from decimal import Decimal
from pathlib import Path

import pytest
import requests
import responses
from sqlalchemy import func, select

from app.models import PriceSnapshot, Product, Retailer, User, Watch
from app.services.auth import create_access_token, create_user

HTML = Path(__file__).resolve().parent.parent / "fixtures" / "html"
URL = "http://shopalpha.mock:8080/items/1001"
GG_URL = "http://gammagoods.mock:8080/items/1003"


def html(name: str) -> str:
    return (HTML / name).read_text()


@pytest.fixture(autouse=True)
def mock_http():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def second_headers(db_session):
    other = create_user(db_session, "other@example.com", "other-password")
    return {"Authorization": f"Bearer {create_access_token(other)}"}


def add(client, headers, url=URL):
    return client.post("/api/v1/products", json={"url": url}, headers=headers)


def test_create_product(client, auth_headers, seed_retailers, mock_http, db_session):
    mock_http.get(URL, body=html("shopalpha_in_stock.html"))
    resp = add(client, auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["url"] == URL
    assert body["title"] == "Acme Noise-Cancelling Headphones"
    assert body["external_id"] == "SA-1001"
    assert body["current_price"] == "129.99"
    assert body["in_stock"] is True
    assert body["last_scraped_at"] is not None
    assert body["retailer"]["domain"] == "shopalpha.mock"
    assert body["retailer"]["name"] == "ShopAlpha"
    assert body["watch"]["target_price"] is None
    assert body["watch"]["notify_on_restock"] is False
    assert body["watch"]["active"] is True
    assert db_session.scalar(select(func.count()).select_from(PriceSnapshot)) == 1
    snap = db_session.scalars(select(PriceSnapshot)).one()
    assert snap.price == Decimal("129.99")
    assert snap.product_id == body["id"]


def test_url_is_normalized(client, auth_headers, seed_retailers, mock_http):
    mock_http.get(URL, body=html("shopalpha_in_stock.html"))
    resp = add(client, auth_headers, "HTTP://ShopAlpha.mock:8080/items/1001/#x")
    assert resp.status_code == 201
    assert resp.json()["url"] == URL
    assert add(client, auth_headers, URL).status_code == 200
    assert len(mock_http.calls) == 1


def test_second_user_reuses_product(
    client, auth_headers, second_headers, seed_retailers, mock_http, db_session
):
    mock_http.get(URL, body=html("shopalpha_in_stock.html"))
    first = add(client, auth_headers)
    second = add(client, second_headers)
    assert second.status_code == 200
    assert len(mock_http.calls) == 1
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["watch"]["id"] != first.json()["watch"]["id"]
    assert db_session.scalar(select(func.count()).select_from(Watch)) == 2
    assert db_session.scalar(select(func.count()).select_from(PriceSnapshot)) == 1


def test_same_user_repost_returns_same_watch(client, auth_headers, seed_retailers, mock_http):
    mock_http.get(URL, body=html("shopalpha_in_stock.html"))
    first = add(client, auth_headers)
    again = add(client, auth_headers)
    assert again.status_code == 200
    assert again.json()["watch"]["id"] == first.json()["watch"]["id"]
    assert len(mock_http.calls) == 1


def test_other_scrapers(client, auth_headers, seed_retailers, mock_http):
    mock_http.get(GG_URL, body=html("gammagoods_out_of_stock.html"))
    body = add(client, auth_headers, GG_URL).json()
    assert body["current_price"] == "1129.99"
    assert body["in_stock"] is False


def test_unsupported_domain(client, auth_headers, seed_retailers):
    resp = add(client, auth_headers, "http://example.com/items/1")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Unsupported retailer: example.com"}


def test_inactive_retailer(client, auth_headers, seed_retailers, db_session):
    retailer = db_session.scalar(select(Retailer).where(Retailer.domain == "shopalpha.mock"))
    retailer.active = False
    db_session.commit()
    resp = add(client, auth_headers)
    assert resp.status_code == 400
    assert "shopalpha.mock" in resp.json()["detail"]


def test_upstream_error_persists_nothing(
    client, auth_headers, seed_retailers, mock_http, db_session
):
    mock_http.get(URL, status=500)
    resp = add(client, auth_headers)
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Failed to scrape product"}
    for model in (Product, PriceSnapshot, Watch):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0


def test_network_error_502(client, auth_headers, seed_retailers, mock_http):
    mock_http.get(URL, body=requests.ConnectionError("boom"))
    assert add(client, auth_headers).status_code == 502


def test_parse_failure_502(client, auth_headers, seed_retailers, mock_http, db_session):
    mock_http.get(URL, body=html("malformed.html"))
    resp = add(client, auth_headers)
    assert resp.status_code == 502
    assert db_session.scalar(select(func.count()).select_from(Product)) == 0


def test_requires_auth(client):
    assert client.post("/api/v1/products", json={"url": URL}).status_code == 401
    assert client.get("/api/v1/products").status_code == 401
    assert client.get("/api/v1/products/1").status_code == 401


@pytest.mark.parametrize(
    "payload",
    [{}, {"url": ""}, {"url": "not-a-url"}, {"url": "ftp://shopalpha.mock/x"}, {"url": 5}],
)
def test_invalid_url_422(client, auth_headers, payload):
    resp = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.fixture
def three_products(client, auth_headers, seed_retailers, mock_http):
    mock_http.get(URL, body=html("shopalpha_in_stock.html"))
    mock_http.get(GG_URL, body=html("gammagoods_out_of_stock.html"))
    mock_http.get("http://betamart.mock:8080/items/1002", body=html("betamart_product.html"))
    ids = [
        add(client, auth_headers, u).json()["id"]
        for u in (URL, GG_URL, "http://betamart.mock:8080/items/1002")
    ]
    return ids


def test_list_pagination(client, auth_headers, three_products):
    resp = client.get("/api/v1/products", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [i["id"] for i in body["items"]] == three_products
    assert "watch" not in body["items"][0]
    page = client.get("/api/v1/products?limit=1&offset=1", headers=auth_headers).json()
    assert page["total"] == 3
    assert [i["id"] for i in page["items"]] == [three_products[1]]


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
def test_list_bad_pagination(client, auth_headers, query):
    assert client.get(f"/api/v1/products?{query}", headers=auth_headers).status_code == 422


def test_list_filters(client, auth_headers, three_products, db_session):
    gg = db_session.scalar(select(Retailer).where(Retailer.scraper_key == "gammagoods"))
    by_id = client.get(f"/api/v1/products?retailer={gg.id}", headers=auth_headers).json()
    assert [i["id"] for i in by_id["items"]] == [three_products[1]]
    by_name = client.get("/api/v1/products?retailer=gammaGOODS", headers=auth_headers).json()
    assert by_name["total"] == 1
    assert client.get("/api/v1/products?retailer=nope", headers=auth_headers).json()["total"] == 0
    out = client.get("/api/v1/products?in_stock=false", headers=auth_headers).json()
    assert [i["id"] for i in out["items"]] == [three_products[1]]
    inn = client.get("/api/v1/products?in_stock=true", headers=auth_headers).json()
    assert inn["total"] == 2


def test_detail(client, auth_headers, three_products):
    resp = client.get(f"/api/v1/products/{three_products[0]}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_price"] == "129.99"
    assert body["retailer"]["name"] == "ShopAlpha"
    assert "watch" not in body


def test_detail_404(client, auth_headers):
    resp = client.get("/api/v1/products/99999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Product not found"}


def test_unused_user_import():
    assert User
