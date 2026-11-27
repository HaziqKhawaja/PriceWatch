import pytest

from app.services.products import normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://shopalpha.mock:8080/items/1", "http://shopalpha.mock:8080/items/1"),
        ("HTTP://ShopAlpha.MOCK:8080/items/1", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock:8080/items/1/", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock:8080/items/1#reviews", "http://shopalpha.mock:8080/items/1"),
        ("http://shopalpha.mock/", "http://shopalpha.mock"),
        ("http://shopalpha.mock", "http://shopalpha.mock"),
        ("http://shopalpha.mock/Items/A?x=1&y=2", "http://shopalpha.mock/Items/A?x=1&y=2"),
        ("  http://shopalpha.mock/items/1/#top ", "http://shopalpha.mock/items/1"),
        ("http://u:p@shopalpha.mock/a", "http://u:p@shopalpha.mock/a"),
        ("http://[::1]:80/a", "http://[::1]:80/a"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected
