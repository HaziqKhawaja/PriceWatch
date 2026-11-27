from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ParseError, ScrapeResult, parse_price


class BetaMartScraper(BaseScraper):
    key = "betamart"
    domain = "betamart.mock"

    def parse(self, html: str) -> ScrapeResult:
        soup = BeautifulSoup(html, "html.parser")
        node = soup.find(id="product")
        if node is None:
            raise ParseError("No #product element")
        price = parse_price(node.get("data-price"))
        stock = node.get("data-stock")
        if stock not in ("in_stock", "out_of_stock"):
            raise ParseError(f"Invalid data-stock: {stock!r}")
        heading = node.find(attrs={"data-title": True})
        title = heading.get_text(strip=True) if heading else ""
        if not title:
            raise ParseError("Missing title")
        sku = node.get("data-sku")
        return ScrapeResult(
            price=price,
            in_stock=stock == "in_stock",
            title=title,
            external_id=str(sku) if sku else None,
            currency=str(node.get("data-currency") or "USD"),
        )
