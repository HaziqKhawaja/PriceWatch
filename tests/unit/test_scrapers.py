from decimal import Decimal
from pathlib import Path

import pytest

from app.scrapers.base import ParseError, ScrapeResult
from app.scrapers.betamart import BetaMartScraper
from app.scrapers.gammagoods import GammaGoodsScraper
from app.scrapers.shopalpha import ShopAlphaScraper

HTML = Path(__file__).resolve().parent.parent / "fixtures" / "html"


def load(name: str) -> str:
    return (HTML / name).read_text()


@pytest.mark.parametrize(
    ("scraper", "fixture", "expected"),
    [
        (
            ShopAlphaScraper(),
            "shopalpha_in_stock.html",
            ScrapeResult(Decimal("129.99"), True, "Acme Noise-Cancelling Headphones", "SA-1001"),
        ),
        (
            ShopAlphaScraper(),
            "shopalpha_out_of_stock.html",
            ScrapeResult(Decimal("129.99"), False, "Acme Noise-Cancelling Headphones", "SA-1001"),
        ),
        (
            BetaMartScraper(),
            "betamart_product.html",
            ScrapeResult(Decimal("249.50"), True, "Zenith Mechanical Keyboard", "BM-1001"),
        ),
        (
            BetaMartScraper(),
            "betamart_out_of_stock.html",
            ScrapeResult(Decimal("249.50"), False, "Zenith Mechanical Keyboard", "BM-1001"),
        ),
        (
            GammaGoodsScraper(),
            "gammagoods_product.html",
            ScrapeResult(Decimal("1129.99"), True, "Orion 4K Monitor", "GG-1001"),
        ),
        (
            GammaGoodsScraper(),
            "gammagoods_out_of_stock.html",
            ScrapeResult(Decimal("1129.99"), False, "Orion 4K Monitor", "GG-1001"),
        ),
    ],
)
def test_parse_fixtures(scraper, fixture, expected):
    result = scraper.parse(load(fixture))
    assert result == expected
    assert result.price.as_tuple().exponent == -2


@pytest.mark.parametrize("scraper", [ShopAlphaScraper(), BetaMartScraper(), GammaGoodsScraper()])
def test_malformed_raises(scraper):
    with pytest.raises(ParseError):
        scraper.parse(load("malformed.html"))


@pytest.mark.parametrize("scraper", [ShopAlphaScraper(), BetaMartScraper(), GammaGoodsScraper()])
def test_empty_raises(scraper):
    with pytest.raises(ParseError):
        scraper.parse("")


def test_shopalpha_missing_price():
    html = load("shopalpha_in_stock.html").replace('"price": "129.99",', "")
    with pytest.raises(ParseError):
        ShopAlphaScraper().parse(html)


def test_shopalpha_invalid_price_and_json():
    html = load("shopalpha_in_stock.html").replace("129.99", "abc")
    with pytest.raises(ParseError):
        ShopAlphaScraper().parse(html)
    bad = '<script type="application/ld+json">{not json</script>'
    with pytest.raises(ParseError):
        ShopAlphaScraper().parse(bad)


def test_shopalpha_list_and_graph_forms():
    product = (
        '{"@type": "Product", "name": "X", "sku": "S1", "offers": '
        '{"price": "10", "availability": "https://schema.org/InStock"}}'
    )
    as_list = f'<script type="application/ld+json">[{{"@type":"Thing"}}, {product}]</script>'
    result = ShopAlphaScraper().parse(as_list)
    assert result.price == Decimal("10.00")
    graph = f'<script type="application/ld+json">{{"@graph": [{product}]}}</script>'
    assert ShopAlphaScraper().parse(graph).title == "X"


def test_betamart_missing_price():
    html = load("betamart_product.html").replace('data-price="249.50"', "")
    with pytest.raises(ParseError):
        BetaMartScraper().parse(html)


def test_betamart_bad_stock_and_title():
    html = load("betamart_product.html").replace("in_stock", "maybe")
    with pytest.raises(ParseError):
        BetaMartScraper().parse(html)
    html = load("betamart_product.html").replace("Zenith Mechanical Keyboard", "")
    with pytest.raises(ParseError):
        BetaMartScraper().parse(html)


def test_gammagoods_missing_price():
    html = load("gammagoods_product.html").replace('<span class="price">$1,129.99</span>', "")
    with pytest.raises(ParseError):
        GammaGoodsScraper().parse(html)


def test_gammagoods_bad_price_stock_title():
    scraper = GammaGoodsScraper()
    with pytest.raises(ParseError):
        scraper.parse(load("gammagoods_product.html").replace("$1,129.99", "free"))
    with pytest.raises(ParseError):
        scraper.parse(load("gammagoods_product.html").replace("In stock", "Backordered"))
    with pytest.raises(ParseError):
        scraper.parse(load("gammagoods_product.html").replace("Orion 4K Monitor", ""))
    no_stock = load("gammagoods_product.html").replace('class="stock-status"', 'class="x"')
    with pytest.raises(ParseError):
        scraper.parse(no_stock)
