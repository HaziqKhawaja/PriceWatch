import logging
import time

import requests

from app.config import get_settings
from app.scrapers.base import BaseScraper, ScrapeResult

USER_AGENT = "PriceWatch/0.1 (+mock)"

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class FetchError(Exception):
    """Raised when a product page cannot be fetched."""


_sleep = time.sleep  # patchable in tests


def _fetch_once(url: str) -> tuple[str | None, str | None, bool]:
    """Return (body, error, retriable)."""
    try:
        response = _session.get(url, timeout=get_settings().SCRAPER_TIMEOUT_SECONDS)
    except (requests.ConnectionError, requests.Timeout) as exc:
        return None, f"Network error fetching {url}: {exc}", True
    except requests.RequestException as exc:
        return None, f"Network error fetching {url}: {exc}", False
    if response.ok:
        return response.text, None, False
    return None, f"HTTP {response.status_code} fetching {url}", response.status_code >= 500


def fetch_html(url: str) -> str:
    """Fetch a page, retrying transient failures (network errors, HTTP 5xx) with backoff."""
    max_retries = get_settings().SCRAPER_MAX_RETRIES
    attempt = 0
    while True:
        body, error, retriable = _fetch_once(url)
        if body is not None:
            return body
        if not retriable or attempt >= max_retries:
            raise FetchError(error)
        delay = 2**attempt
        logger.warning(
            "Fetch failed (%s); retry %d/%d in %ds", error, attempt + 1, max_retries, delay
        )
        _sleep(delay)
        attempt += 1


def scrape(url: str, scraper: BaseScraper) -> ScrapeResult:
    """Fetch and parse; raises FetchError or ParseError."""
    return scraper.parse(fetch_html(url))
