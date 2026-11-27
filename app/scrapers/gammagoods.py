from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ParseError, ScrapeResult, parse_price


class GammaGoodsScraper(BaseScraper):
    key = "gammagoods"
    domain = "gammagoods.mock"

    def parse(self, html: str) -> ScrapeResult:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("div.product")
        if root is None:
            raise ParseError("No div.product element")
        price_el = root.select_one(".price")
        if price_el is None:
            raise ParseError("Missing price")
        price = parse_price(price_el.get_text(strip=True))
        stock_el = root.select_one(".stock-status")
        if stock_el is None:
            raise ParseError("Missing stock status")
        stock = " ".join(stock_el.get_text().split()).lower()
        if stock not in ("in stock", "out of stock"):
            raise ParseError(f"Unrecognized stock status: {stock!r}")
        title_el = root.select_one(".product-title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            raise ParseError("Missing title")
        sku_el = root.select_one(".sku")
        sku = sku_el.get_text(strip=True) if sku_el else ""
        return ScrapeResult(
            price=price,
            in_stock=stock == "in stock",
            title=title,
            external_id=sku or None,
        )
