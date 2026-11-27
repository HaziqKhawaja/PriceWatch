import requests

from app.config import get_settings
from app.scrapers.base import BaseScraper, ScrapeResult

USER_AGENT = "PriceWatch/0.1 (+mock)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class FetchError(Exception):
    """Raised when a product page cannot be fetched."""


def fetch_html(url: str) -> str:
    """Fetch a page. Single seam where milestone 4 adds retries/backoff."""
    try:
        response = _session.get(url, timeout=get_settings().SCRAPER_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise FetchError(f"Network error fetching {url}: {exc}") from exc
    if not response.ok:
        raise FetchError(f"HTTP {response.status_code} fetching {url}")
    return response.text


def scrape(url: str, scraper: BaseScraper) -> ScrapeResult:
    """Fetch and parse; raises FetchError or ParseError."""
    return scraper.parse(fetch_html(url))
