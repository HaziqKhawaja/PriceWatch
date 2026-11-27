import pytest

from app.models import Product, Retailer, Watch
from app.services.auth import create_access_token, create_user

URL = "/api/v1/watches"


@pytest.fixture
def product(db_session):
    retailer = Retailer(
        name="R", domain="r.mock", scraper_key="shopalpha", active=True, rate_limit_seconds=1
    )
    db_session.add(retailer)
    db_session.flush()
    p = Product(
        retailer_id=retailer.id,
        url="http://r.mock/1",
        title="Widget",
        current_price="10.00",
        in_stock=True,
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def other(db_session):
    return create_user(db_session, "other@example.com", "other-password")


@pytest.fixture
def other_headers(other):
    return {"Authorization": f"Bearer {create_access_token(other)}"}


def make_watch(db_session, user, product, **kw):
    w = Watch(user_id=user.id, product_id=product.id, **kw)
    db_session.add(w)
    db_session.flush()
    db_session.refresh(w)
    return w


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", URL),
        ("post", URL),
        ("patch", f"{URL}/1"),
        ("delete", f"{URL}/1"),
    ],
)
def test_requires_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_create(client, auth_headers, product):
    resp = client.post(
        URL,
        json={
            "product_id": product.id,
            "target_price": 5.5,
            "notify_on_restock": True,
            "webhook_url": "https://hooks.example.com/x",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["product_id"] == product.id
    assert body["target_price"] == "5.50"
    assert body["notify_on_restock"] is True
    assert body["webhook_url"] == "https://hooks.example.com/x"
    assert body["active"] is True
    assert body["price_alert_active"] is False
    assert body["created_at"]
    assert body["product"] == {
        "id": product.id,
        "title": "Widget",
        "url": "http://r.mock/1",
        "current_price": "10.00",
        "in_stock": True,
    }


def test_create_defaults(client, auth_headers, product):
    body = client.post(URL, json={"product_id": product.id}, headers=auth_headers).json()
    assert body["target_price"] is None
    assert body["notify_on_restock"] is False
    assert body["webhook_url"] is None


def test_create_unknown_product(client, auth_headers):
    resp = client.post(URL, json={"product_id": 999999}, headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Product not found"


def test_create_duplicate(client, auth_headers, product):
    assert (
        client.post(URL, json={"product_id": product.id}, headers=auth_headers).status_code == 201
    )
    resp = client.post(URL, json={"product_id": product.id}, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Already watching this product"


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)", "nonsense"])
def test_create_invalid_webhook(client, auth_headers, product, url):
    resp = client.post(
        URL, json={"product_id": product.id, "webhook_url": url}, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("price", [0, -1, 1.005, "1.234"])
def test_create_invalid_target(client, auth_headers, product, price):
    resp = client.post(
        URL, json={"product_id": product.id, "target_price": price}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_list_only_own_and_pagination(client, auth_headers, db_session, user, other, product):
    p2 = Product(retailer_id=product.retailer_id, url="http://r.mock/2", title="Two", in_stock=None)
    db_session.add(p2)
    db_session.flush()
    w1 = make_watch(db_session, user, product)
    w2 = make_watch(db_session, user, p2)
    make_watch(db_session, other, product)
    body = client.get(URL, headers=auth_headers).json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [w1.id, w2.id]
    assert body["items"][1]["product"]["current_price"] is None
    page = client.get(URL, params={"limit": 1, "offset": 1}, headers=auth_headers).json()
    assert [i["id"] for i in page["items"]] == [w2.id]
    assert page["total"] == 2
    assert page["limit"] == 1
    assert page["offset"] == 1


def test_patch_updates(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product)
    resp = client.patch(
        f"{URL}/{w.id}",
        json={
            "target_price": "7.25",
            "notify_on_restock": True,
            "webhook_url": "http://h.example/x",
            "active": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_price"] == "7.25"
    assert body["notify_on_restock"] is True
    assert body["webhook_url"] == "http://h.example/x"
    assert body["active"] is False


def test_patch_explicit_null_clears(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", webhook_url="http://h/x")
    body = client.patch(
        f"{URL}/{w.id}", json={"target_price": None, "webhook_url": None}, headers=auth_headers
    ).json()
    assert body["target_price"] is None
    assert body["webhook_url"] is None


def test_patch_omitted_leaves_values(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", webhook_url="http://h/x")
    body = client.patch(f"{URL}/{w.id}", json={"active": False}, headers=auth_headers).json()
    assert body["target_price"] == "5.00"
    assert body["webhook_url"] == "http://h/x"


@pytest.mark.parametrize("field", ["active", "notify_on_restock"])
def test_patch_null_bool_rejected(client, auth_headers, db_session, user, product, field):
    w = make_watch(db_session, user, product)
    resp = client.patch(f"{URL}/{w.id}", json={field: None}, headers=auth_headers)
    assert resp.status_code == 422


def test_patch_invalid_values(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product)
    assert (
        client.patch(f"{URL}/{w.id}", json={"target_price": 0}, headers=auth_headers).status_code
        == 422
    )
    assert (
        client.patch(
            f"{URL}/{w.id}", json={"webhook_url": "ftp://x/y"}, headers=auth_headers
        ).status_code
        == 422
    )


def test_patch_changing_target_resets_alert(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", price_alert_active=True)
    body = client.patch(f"{URL}/{w.id}", json={"target_price": "4.00"}, headers=auth_headers).json()
    assert body["price_alert_active"] is False


def test_patch_clearing_target_resets_alert(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", price_alert_active=True)
    body = client.patch(f"{URL}/{w.id}", json={"target_price": None}, headers=auth_headers).json()
    assert body["price_alert_active"] is False


def test_patch_without_target_keeps_alert(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", price_alert_active=True)
    body = client.patch(f"{URL}/{w.id}", json={"active": False}, headers=auth_headers).json()
    assert body["price_alert_active"] is True


def test_patch_same_target_keeps_alert(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product, target_price="5.00", price_alert_active=True)
    body = client.patch(f"{URL}/{w.id}", json={"target_price": "5.00"}, headers=auth_headers).json()
    assert body["price_alert_active"] is True


def test_other_users_watch_404(client, other_headers, db_session, user, product):
    w = make_watch(db_session, user, product)
    assert (
        client.patch(f"{URL}/{w.id}", json={"active": False}, headers=other_headers).status_code
        == 404
    )
    assert client.delete(f"{URL}/{w.id}", headers=other_headers).status_code == 404
    assert db_session.get(Watch, w.id) is not None


def test_patch_unknown_404(client, auth_headers):
    assert client.patch(f"{URL}/999999", json={}, headers=auth_headers).status_code == 404


def test_delete(client, auth_headers, db_session, user, product):
    w = make_watch(db_session, user, product)
    assert client.delete(f"{URL}/{w.id}", headers=auth_headers).status_code == 204
    assert client.delete(f"{URL}/{w.id}", headers=auth_headers).status_code == 404
