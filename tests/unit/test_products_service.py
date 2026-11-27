import pytest

from app.services.products import normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://shopalpha.mock:8080/items/1", "http://shopalpha.mock:8080/items/1"),
        ("HTTP://ShopAlpha.MOCK:8080/items/1", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock:8080/items/1/", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock:8080/items/1#reviews", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock/", "http://shopalpha.mock"),
        ("http://shopalpha.mock", "http://shopalpha.mock"),
        ("http://shopalpha.mock/Items/A?x=1&y=2", "http://shopalpha.mock/Items/A?x=1&y=2"),
        ("  http://shopalpha.mock/items/1/#top ", "http://shopalpha.mock/items/1"),
        ("http://u:p@shopalpha.mock/a", "http://u:p@shopalpha.mock/a"),
        ("http://[::1]:80/a", "http://[::1]:80/a"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_add_product_race_reuses_existing(db_session, user, seed_retailers, monkeypatch):
    from decimal import Decimal

    from sqlalchemy import select

    from app.models import Product, Retailer
    from app.scrapers.base import ScrapeResult
    from app.services import products as svc

    url = "http://shopalpha.mock:8080/items/race"

    def racing_scrape(u, scraper):
        retailer = db_session.scalar(select(Retailer).where(Retailer.domain == "shopalpha.mock"))
        db_session.add(Product(retailer=retailer, url=u, title="Winner"))
        db_session.flush()
        return ScrapeResult(Decimal("5.00"), True, "Loser", "X")

    monkeypatch.setattr(svc, "scrape", racing_scrape)
    product, watch, created = svc.add_product_for_user(db_session, user, url)
    assert created is False
    assert product.title == "Winner"
    assert watch.product_id == product.id


def test_unknown_scraper_key_is_unsupported(db_session, user):
    from app.models import Retailer
    from app.services import products as svc

    db_session.add(
        Retailer(
            name="Ghost",
            domain="ghost.mock",
            scraper_key="nonexistent",
            active=True,
            rate_limit_seconds=1,
        )
    )
    db_session.flush()
    with pytest.raises(svc.UnsupportedRetailerError):
        svc.add_product_for_user(db_session, user, "http://ghost.mock/items/1")


def test_integrity_error_without_winner_is_reraised(db_session, user, seed_retailers, monkeypatch):
    from decimal import Decimal

    from sqlalchemy.exc import IntegrityError

    from app.scrapers.base import ScrapeResult
    from app.services import products as svc

    # A NOT NULL violation (not a duplicate URL) leaves no existing row to reuse.
    monkeypatch.setattr(
        svc, "scrape", lambda url, scraper: ScrapeResult(Decimal("5.00"), True, None, "X")
    )
    with pytest.raises(IntegrityError):
        svc.add_product_for_user(db_session, user, "http://shopalpha.mock:8080/items/9")
