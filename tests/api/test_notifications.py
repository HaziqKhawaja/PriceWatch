from datetime import UTC, datetime, timedelta

import pytest

from app.models import Notification, Product, Retailer, Watch
from app.services.auth import create_access_token, create_user

URL = "/api/v1/notifications"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def other(db_session):
    return create_user(db_session, "other@example.com", "other-password")


@pytest.fixture
def other_headers(other):
    return {"Authorization": f"Bearer {create_access_token(other)}"}


@pytest.fixture
def product(db_session):
    retailer = Retailer(
        name="R", domain="r.mock", scraper_key="shopalpha", active=True, rate_limit_seconds=1
    )
    db_session.add(retailer)
    db_session.flush()
    p = Product(retailer_id=retailer.id, url="http://r.mock/1", title="Widget")
    db_session.add(p)
    db_session.flush()
    return p


def notify(db_session, user, product, minutes=0, **kw):
    watch = db_session.query(Watch).filter_by(user_id=user.id, product_id=product.id).first()
    if watch is None:
        watch = Watch(user_id=user.id, product_id=product.id)
        db_session.add(watch)
        db_session.flush()
    n = Notification(
        watch_id=watch.id,
        type=kw.pop("type", "price_drop"),
        message=kw.pop("message", "msg"),
        created_at=NOW + timedelta(minutes=minutes),
        **kw,
    )
    db_session.add(n)
    db_session.flush()
    return n


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
    assert client.post(f"{URL}/1/read").status_code == 401


def test_list_own_newest_first(client, auth_headers, db_session, user, other, product):
    old = notify(db_session, user, product, minutes=0, price="9.99", delivery_error="HTTP 500")
    new = notify(db_session, user, product, minutes=5, type="restock", message="back")
    notify(db_session, other, product, minutes=10)
    body = client.get(URL, headers=auth_headers).json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [new.id, old.id]
    first, second = body["items"]
    assert first["product_title"] == "Widget"
    assert first["product_id"] == product.id
    assert first["watch_id"] == new.watch_id
    assert first["type"] == "restock"
    assert first["price"] is None
    assert first["delivered"] is False
    assert first["read_at"] is None
    assert second["price"] == "9.99"
    assert second["delivery_error"] == "HTTP 500"


def test_list_tiebreak_and_pagination(client, auth_headers, db_session, user, product):
    a = notify(db_session, user, product)
    b = notify(db_session, user, product)
    body = client.get(URL, params={"limit": 1}, headers=auth_headers).json()
    assert [i["id"] for i in body["items"]] == [b.id]
    assert body["total"] == 2
    body = client.get(URL, params={"limit": 1, "offset": 1}, headers=auth_headers).json()
    assert [i["id"] for i in body["items"]] == [a.id]


def test_unread_filter(client, auth_headers, db_session, user, product):
    read = notify(db_session, user, product, minutes=0, read_at=NOW)
    unread = notify(db_session, user, product, minutes=1)

    def ids(params):
        resp = client.get(URL, params=params, headers=auth_headers)
        return [i["id"] for i in resp.json()["items"]]

    assert ids({"unread": "true"}) == [unread.id]
    assert ids({"unread": "false"}) == [unread.id, read.id]
    assert ids({}) == [unread.id, read.id]


def test_mark_read_idempotent(client, auth_headers, db_session, user, product):
    n = notify(db_session, user, product)
    first = client.post(f"{URL}/{n.id}/read", headers=auth_headers)
    assert first.status_code == 200
    stamp = first.json()["read_at"]
    assert stamp is not None
    assert first.json()["product_title"] == "Widget"
    second = client.post(f"{URL}/{n.id}/read", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["read_at"] == stamp


def test_mark_read_other_user_404(client, other_headers, db_session, user, product):
    n = notify(db_session, user, product)
    assert client.post(f"{URL}/{n.id}/read", headers=other_headers).status_code == 404
    db_session.refresh(n)
    assert n.read_at is None


def test_mark_read_unknown_404(client, auth_headers):
    assert client.post(f"{URL}/999999/read", headers=auth_headers).status_code == 404
