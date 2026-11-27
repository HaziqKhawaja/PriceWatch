import pytest

from app.scrapers.registry import get_scraper_by_key, get_scraper_for_url


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("http://shopalpha.mock:8080/items/1001", "shopalpha"),
        ("http://shopalpha.mock/items/1001", "shopalpha"),
        ("https://SHOPALPHA.mock:9999/items/1", "shopalpha"),
        ("http://betamart.mock:8080/items/1002", "betamart"),
        ("http://gammagoods.mock:8080/items/1003", "gammagoods"),
    ],
)
def test_url_resolves(url, key):
    scraper = get_scraper_for_url(url)
    assert scraper is not None
    assert scraper.key == key


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/items/1",
        "http://evil.shopalpha.mock/items/1",
        "http://shopalpha.mock.evil.com/",
        "not a url",
        "http://[bad/",
    ],
)
def test_unknown_url(url):
    assert get_scraper_for_url(url) is None


def test_by_key():
    assert get_scraper_by_key("betamart").key == "betamart"
    assert get_scraper_by_key("nope") is None
