from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PriceSnapshot, Product, Retailer, User, Watch
from app.scrapers.base import ParseError
from app.scrapers.registry import get_scraper_by_key
from app.services.scraping import FetchError, scrape


class UnsupportedRetailerError(Exception):
    def __init__(self, host: str):
        super().__init__(f"Unsupported retailer: {host}")
        self.host = host


class ScrapeFailedError(Exception):
    pass


def normalize_url(url: str) -> str:
    """Lowercase scheme and host; drop fragment and trailing slash; keep port/path/query."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"
    if parts.username:
        userinfo = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{userinfo}@{netloc}"
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def add_product_for_user(db: Session, user: User, url: str) -> tuple[Product, Watch, bool]:
    normalized = normalize_url(url)
    host = (urlsplit(normalized).hostname or "").lower()
    retailer = db.scalar(select(Retailer).where(Retailer.domain == host, Retailer.active.is_(True)))
    if retailer is None:
        raise UnsupportedRetailerError(host)

    product = db.scalar(select(Product).where(Product.url == normalized))
    created = product is None
    if product is None:
        scraper = get_scraper_by_key(retailer.scraper_key)
        if scraper is None:
            raise UnsupportedRetailerError(host)
        try:
            result = scrape(normalized, scraper)
        except (FetchError, ParseError) as exc:
            raise ScrapeFailedError(str(exc)) from exc
        now = datetime.now(UTC)
        product = Product(
            retailer=retailer,
            url=normalized,
            title=result.title,
            external_id=result.external_id,
            current_price=result.price,
            in_stock=result.in_stock,
            last_scraped_at=now,
        )
        product.snapshots.append(
            PriceSnapshot(price=result.price, in_stock=result.in_stock, scraped_at=now)
        )
        db.add(product)
        db.flush()

    watch = db.scalar(select(Watch).where(Watch.user_id == user.id, Watch.product_id == product.id))
    if watch is None:
        watch = Watch(user_id=user.id, product_id=product.id)
        db.add(watch)
    db.commit()
    db.refresh(product)
    db.refresh(watch)
    return product, watch, created
