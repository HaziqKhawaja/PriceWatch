import pytest
from pydantic import ValidationError

from app.schemas.admin import RetailerCreate
from app.schemas.product import ProductCreate


@pytest.mark.parametrize("url", ["http://[::1/x", "ftp://shopalpha.mock/x", "http:///nohost"])
def test_product_create_rejects_bad_urls(url):
    with pytest.raises(ValidationError):
        ProductCreate(url=url)


@pytest.mark.parametrize("domain", ["-bad.mock", "bad..mock", "bad_domain.mock", ""])
def test_retailer_domain_rejects_invalid(domain):
    with pytest.raises(ValidationError):
        RetailerCreate(name="X", domain=domain, scraper_key="shopalpha")
