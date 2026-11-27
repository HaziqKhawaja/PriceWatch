import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

CENT = Decimal("0.01")


class ParseError(Exception):
    """Raised when a page cannot be parsed into a ScrapeResult."""


@dataclass(frozen=True)
class ScrapeResult:
    price: Decimal
    in_stock: bool
    title: str
    external_id: str | None
    currency: str = "USD"


def parse_price(raw: object) -> Decimal:
    """Parse a price like '129.99' or '$1,129.99' into a Decimal quantized to 0.01."""
    if raw is None:
        raise ParseError("Missing price")
    text = re.sub(r"[\s$,]", "", str(raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ParseError(f"Invalid price: {raw!r}") from None
    if not value.is_finite() or value < 0:
        raise ParseError(f"Invalid price: {raw!r}")
    return value.quantize(CENT)


class BaseScraper(ABC):
    key: str  # matches retailers.scraper_key
    domain: str  # hostname served by this scraper

    def matches(self, url: str) -> bool:
        try:
            host = urlsplit(url).hostname
        except ValueError:
            return False
        return host is not None and host.lower() == self.domain.lower()

    @abstractmethod
    def parse(self, html: str) -> ScrapeResult:
        """Parse product HTML; raise ParseError on missing or invalid data."""
