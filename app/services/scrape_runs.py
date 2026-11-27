import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import PriceSnapshot, Product, Retailer, ScrapeRun
from app.scrapers.registry import get_scraper_by_key
from app.services import alerts, webhooks
from app.services.rate_limit import rate_limiter
from app.services.scraping import scrape

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=60)
ERROR_SUMMARY_LIMIT = 4000
TRUNCATED_SUFFIX = "...(truncated)"
START_RUN_LOCK_KEY = 0x5052_4943  # pg advisory lock serializing run starts


class RunInProgressError(Exception):
    """A scrape run is already active (finished_at IS NULL and started < 60 min ago)."""


def start_scrape_run(db: Session) -> ScrapeRun:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": START_RUN_LOCK_KEY})
    now = datetime.now(UTC)
    active = db.scalar(
        select(ScrapeRun.id)
        .where(ScrapeRun.finished_at.is_(None), ScrapeRun.started_at > now - STALE_AFTER)
        .limit(1)
    )
    if active is not None:
        db.rollback()
        raise RunInProgressError()
    run = ScrapeRun(started_at=now, products_attempted=0, succeeded=0, failed=0, error_summary=None)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _summary(errors: list[str]) -> str | None:
    if not errors:
        return None
    text = "\n".join(errors)
    if len(text) > ERROR_SUMMARY_LIMIT:
        text = text[: ERROR_SUMMARY_LIMIT - len(TRUNCATED_SUFFIX)] + TRUNCATED_SUFFIX
    return text


def _scrape_product(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    retailer = db.get(Retailer, product.retailer_id)
    scraper = get_scraper_by_key(retailer.scraper_key)
    if scraper is None:
        raise LookupError(f"No scraper for key {retailer.scraper_key!r}")
    rate_limiter.wait(retailer.domain, retailer.rate_limit_seconds)
    result = scrape(product.url, scraper)

    previous = db.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product.id)
        .order_by(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())
        .limit(1)
    )
    now = datetime.now(UTC)
    snapshot = PriceSnapshot(
        product_id=product.id, price=result.price, in_stock=result.in_stock, scraped_at=now
    )
    db.add(snapshot)
    product.current_price = result.price
    product.in_stock = result.in_stock
    product.last_scraped_at = now
    if result.title and result.title != product.title:
        product.title = result.title
    db.flush()
    notification_ids = alerts.evaluate_watches(db, product, previous, snapshot)
    db.commit()
    try:
        webhooks.deliver_notifications(db, notification_ids)
    except Exception:
        db.rollback()
        logger.exception("Webhook delivery failed for product %s", product_id)


def execute_scrape_run(
    run_id: int,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    db = session_factory()
    attempted = succeeded = failed = 0
    errors: list[str] = []
    try:
        try:
            rows = db.execute(
                select(Product.id, Product.url)
                .join(Retailer, Product.retailer_id == Retailer.id)
                .where(Retailer.active.is_(True))
                .order_by(Retailer.id, Product.id)
            ).all()
            for product_id, url in rows:
                attempted += 1
                try:
                    _scrape_product(db, product_id)
                    succeeded += 1
                except Exception as exc:
                    db.rollback()
                    failed += 1
                    errors.append(f"{product_id} {url}: {type(exc).__name__}: {exc}")
                    logger.warning("Scrape failed for product %s: %s", product_id, exc)
        except Exception as exc:
            db.rollback()
            logger.exception("Scrape run %s aborted", run_id)
            errors.append(f"run aborted: {type(exc).__name__}: {exc}")
        finally:
            run = db.get(ScrapeRun, run_id)
            if run is not None:
                run.products_attempted = attempted
                run.succeeded = succeeded
                run.failed = failed
                run.error_summary = _summary(errors)
                run.finished_at = datetime.now(UTC)
                db.commit()
        logger.info(
            "Scrape run %s finished: attempted=%d succeeded=%d failed=%d",
            run_id,
            attempted,
            succeeded,
            failed,
        )
    finally:
        db.close()


def run_scrape_cycle(session_factory: Callable[[], Session] = SessionLocal) -> int | None:
    db = session_factory()
    try:
        run = start_scrape_run(db)
        run_id = run.id
    except RunInProgressError:
        logger.info("Scrape cycle skipped: a run is already in progress")
        return None
    finally:
        db.close()
    execute_scrape_run(run_id, session_factory)
    return run_id
