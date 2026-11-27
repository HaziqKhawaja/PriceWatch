from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import responses
from sqlalchemy import select

from app.models import PriceSnapshot, Product, Retailer, ScrapeRun
from app.services import scrape_runs
from app.services.rate_limit import DomainRateLimiter
from app.services.scrape_runs import (
    RunInProgressError,
    execute_scrape_run,
    run_scrape_cycle,
    start_scrape_run,
)

HTML = Path(__file__).resolve().parent.parent / "fixtures" / "html"
SA = "http://shopalpha.mock:8080/items/1"
BM = "http://betamart.mock:8080/items/2"
GG = "http://gammagoods.mock:8080/items/3"


def html(name):
    return (HTML / name).read_text()


class KeepOpen:
    """Session wrapper whose close() is a no-op so writes stay in the test transaction."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass


@pytest.fixture
def factory(db_session):
    return lambda: KeepOpen(db_session)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(scrape_runs, "rate_limiter", DomainRateLimiter(sleep=lambda s: None))
    from app.services import scraping

    monkeypatch.setattr(scraping, "_sleep", lambda s: None)


@pytest.fixture
def evaluate_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scrape_runs.alerts,
        "evaluate_watches",
        lambda db, product, previous, current: calls.append((product.id, previous, current)) or [],
    )
    return calls


def make_product(db, domain, url, title="Old title", price="1.00"):
    retailer = db.scalar(select(Retailer).where(Retailer.domain == domain))
    p = Product(retailer=retailer, url=url, title=title, current_price=Decimal(price))
    db.add(p)
    db.commit()
    return p


def new_run(db):
    return start_scrape_run(db)


@responses.activate
def test_all_succeed(db_session, seed_retailers, factory, evaluate_calls):
    p1 = make_product(db_session, "shopalpha.mock", SA)
    p2 = make_product(db_session, "betamart.mock", BM)
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    responses.get(BM, body=html("betamart_product.html"))
    run = new_run(db_session)

    execute_scrape_run(run.id, factory)

    db_session.refresh(run)
    assert (run.products_attempted, run.succeeded, run.failed) == (2, 2, 0)
    assert run.error_summary is None
    assert run.finished_at is not None
    for p in (p1, p2):
        db_session.refresh(p)
        assert p.last_scraped_at is not None
        assert p.current_price is not None
        assert p.in_stock is not None
        assert (
            len(
                db_session.scalars(
                    select(PriceSnapshot).where(PriceSnapshot.product_id == p.id)
                ).all()
            )
            == 1
        )
    assert p1.title == "Acme Noise-Cancelling Headphones"
    assert p1.current_price == Decimal("129.99")
    assert len(evaluate_calls) == 2


@responses.activate
def test_failures_isolated(db_session, seed_retailers, factory, evaluate_calls):
    make_product(db_session, "shopalpha.mock", SA)
    bad_fetch = make_product(db_session, "betamart.mock", BM)
    bad_parse = make_product(db_session, "gammagoods.mock", GG)
    ok = make_product(db_session, "shopalpha.mock", SA + "9")
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    responses.get(BM, status=404)
    responses.get(GG, body=html("malformed.html"))
    responses.get(SA + "9", body=html("shopalpha_in_stock.html"))
    run = new_run(db_session)

    execute_scrape_run(run.id, factory)

    db_session.refresh(run)
    assert (run.products_attempted, run.succeeded, run.failed) == (4, 2, 2)
    assert run.finished_at is not None
    assert f"{bad_fetch.id} {BM}: FetchError" in run.error_summary
    assert f"{bad_parse.id} {GG}: ParseError" in run.error_summary
    db_session.refresh(ok)
    assert ok.last_scraped_at is not None
    db_session.refresh(bad_fetch)
    assert bad_fetch.last_scraped_at is None


@responses.activate
def test_inactive_retailer_skipped(db_session, seed_retailers, factory, evaluate_calls):
    make_product(db_session, "shopalpha.mock", SA)
    make_product(db_session, "betamart.mock", BM)
    db_session.scalar(select(Retailer).where(Retailer.domain == "betamart.mock")).active = False
    db_session.commit()
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    run = new_run(db_session)

    execute_scrape_run(run.id, factory)

    db_session.refresh(run)
    assert (run.products_attempted, run.succeeded, run.failed) == (1, 1, 0)
    assert [c.request.url for c in responses.calls] == [SA]


def test_error_summary_truncated(db_session, seed_retailers, factory, evaluate_calls):
    for i in range(80):
        make_product(
            db_session, "shopalpha.mock", f"http://shopalpha.mock:8080/items/x{i}" + "a" * 50
        )
    with responses.RequestsMock(assert_all_requests_are_fired=False):
        run = new_run(db_session)
        execute_scrape_run(run.id, factory)
    db_session.refresh(run)
    assert run.failed == 80
    assert len(run.error_summary) <= 4000
    assert run.error_summary.endswith("...(truncated)")


def test_start_run_in_progress_and_stale(db_session):
    now = datetime.now(UTC)
    stale = ScrapeRun(started_at=now - timedelta(hours=2))
    db_session.add(stale)
    db_session.commit()
    run = start_scrape_run(db_session)
    assert run.finished_at is None
    assert run.products_attempted == 0
    with pytest.raises(RunInProgressError):
        start_scrape_run(db_session)


def test_run_scrape_cycle_skips_when_in_progress(db_session, factory):
    db_session.add(ScrapeRun(started_at=datetime.now(UTC)))
    db_session.commit()
    assert run_scrape_cycle(factory) is None


@responses.activate
def test_run_scrape_cycle_runs(db_session, seed_retailers, factory, evaluate_calls):
    make_product(db_session, "shopalpha.mock", SA)
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    run_id = run_scrape_cycle(factory)
    run = db_session.get(ScrapeRun, run_id)
    assert run.finished_at is not None
    assert run.succeeded == 1


@responses.activate
def test_evaluate_watches_previous(db_session, seed_retailers, factory, evaluate_calls):
    make_product(db_session, "shopalpha.mock", SA)
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    execute_scrape_run(new_run(db_session).id, factory)
    first = evaluate_calls[0]
    assert first[1] is None
    # finish the first run so a second can start
    db_session.query(ScrapeRun).update({"finished_at": datetime.now(UTC)})
    execute_scrape_run(new_run(db_session).id, factory)
    second = evaluate_calls[1]
    assert second[1] is first[2]
    assert second[2] is not first[2]


def _alert_setup(db, hook_status):
    from app.models import Notification, Watch
    from app.services.auth import create_user

    p = make_product(db, "shopalpha.mock", SA)
    u = create_user(db, "alert@example.com", "pw-pw-pw-pw")
    w = Watch(
        user_id=u.id,
        product_id=p.id,
        target_price=Decimal("500"),
        webhook_url="http://hook.example/in",
    )
    db.add(w)
    db.commit()
    responses.get(SA, body=html("shopalpha_in_stock.html"))
    responses.post("http://hook.example/in", status=hook_status)
    return p, Notification


@responses.activate
def test_alert_creates_notification_and_calls_webhook(db_session, seed_retailers, factory):
    p, Notification = _alert_setup(db_session, 200)
    run = new_run(db_session)
    execute_scrape_run(run.id, factory)
    db_session.refresh(run)
    assert (run.succeeded, run.failed) == (1, 0)
    n = db_session.scalar(select(Notification))
    assert n.type == "price_drop"
    assert n.delivered is True
    assert [c.request.url for c in responses.calls] == [SA, "http://hook.example/in"]


@responses.activate
def test_webhook_500_still_counts_success(db_session, seed_retailers, factory):
    p, Notification = _alert_setup(db_session, 500)
    run = new_run(db_session)
    execute_scrape_run(run.id, factory)
    db_session.refresh(run)
    assert (run.succeeded, run.failed) == (1, 0)
    n = db_session.scalar(select(Notification))
    assert n.delivered is False
    assert n.delivery_error == "HTTP 500"
    db_session.refresh(p)
    assert p.last_scraped_at is not None


@responses.activate
def test_webhook_exception_does_not_fail_product(db_session, seed_retailers, factory, monkeypatch):
    _alert_setup(db_session, 200)

    def boom(db, ids):
        raise RuntimeError("boom")

    monkeypatch.setattr(scrape_runs.webhooks, "deliver_notifications", boom)
    run = new_run(db_session)
    execute_scrape_run(run.id, factory)
    db_session.refresh(run)
    assert (run.succeeded, run.failed) == (1, 0)
