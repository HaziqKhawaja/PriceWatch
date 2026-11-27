import json
from typing import Any

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ParseError, ScrapeResult, parse_price


def _is_product(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    node_type = node.get("@type")
    return node_type == "Product" or (isinstance(node_type, list) and "Product" in node_type)


def _find_product(data: Any) -> dict | None:
    if isinstance(data, list):
        for item in data:
            found = _find_product(item)
            if found:
                return found
        return None
    if _is_product(data):
        return data
    if isinstance(data, dict) and isinstance(data.get("@graph"), list):
        return _find_product(data["@graph"])
    return None


class ShopAlphaScraper(BaseScraper):
    key = "shopalpha"
    domain = "shopalpha.mock"

    def parse(self, html: str) -> ScrapeResult:
        soup = BeautifulSoup(html, "html.parser")
        product = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
            except ValueError:
                continue
            product = _find_product(data)
            if product:
                break
        if product is None:
            raise ParseError("No Product JSON-LD found")

        offers = product.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if not isinstance(offers, dict):
            raise ParseError("Product has no offers")

        title = product.get("name")
        if not isinstance(title, str) or not title.strip():
            raise ParseError("Missing title")
        price = parse_price(offers.get("price"))
        availability = offers.get("availability")
        if not isinstance(availability, str):
            raise ParseError("Missing availability")
        in_stock = availability.rsplit("/", 1)[-1] == "InStock"
        sku = product.get("sku")
        currency = offers.get("priceCurrency") or "USD"
        return ScrapeResult(
            price=price,
            in_stock=in_stock,
            title=title.strip(),
            external_id=str(sku) if sku else None,
            currency=str(currency),
        )
