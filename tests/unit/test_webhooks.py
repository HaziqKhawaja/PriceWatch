import json
from datetime import UTC
from decimal import Decimal

import pytest
import requests
import responses
from sqlalchemy import select

from app.models import Notification, PriceSnapshot, Product, Retailer, Watch
from app.services import webhooks
from app.services.auth import create_user

URL = "http://hook.example/in"


@pytest.fixture
def setup(db_session, seed_retailers):
    retailer = db_session.scalar(select(Retailer).where(Retailer.domain == "shopalpha.mock"))
    p = Product(
        retailer=retailer,
        url="http://shopalpha.mock:8080/items/4412",
        title="Acme Wireless Headphones",
        current_price=Decimal("49.99"),
        in_stock=True,
    )
    db_session.add(p)
    db_session.flush()
    db_session.add_all(
        [
            PriceSnapshot(product_id=p.id, price=Decimal("54.99"), in_stock=True),
            PriceSnapshot(product_id=p.id, price=Decimal("49.99"), in_stock=True),
        ]
    )
    u = create_user(db_session, "w@example.com", "pw-pw-pw-pw")

    def make(webhook_url=URL):
        w = Watch(
            user_id=u.id, product_id=p.id, target_price=Decimal("50"), webhook_url=webhook_url
        )
        db_session.add(w)
        db_session.flush()
        n = Notification(watch_id=w.id, type="price_drop", message="m", price=Decimal("49.99"))
        db_session.add(n)
        db_session.flush()
        db_session.refresh(n)
        return p, w, n

    return make


@responses.activate
def test_success_payload(db_session, setup):
    p, w, n = setup()
    responses.post(URL, status=200)
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is True and n.delivery_error is None
    req = responses.calls[0].request
    assert req.headers["Content-Type"] == "application/json"
    assert req.headers["User-Agent"].startswith("PriceWatch/")
    assert json.loads(req.body) == {
        "type": "price_drop",
        "notification_id": n.id,
        "watch_id": w.id,
        "product": {
            "id": p.id,
            "title": "Acme Wireless Headphones",
            "url": "http://shopalpha.mock:8080/items/4412",
            "retailer": "ShopAlpha",
        },
        "price": 49.99,
        "target_price": 50.0,
        "previous_price": 54.99,
        "in_stock": True,
        "currency": "USD",
        "triggered_at": n.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    assert json.loads(req.body)["triggered_at"].endswith("Z")


@responses.activate
def test_http_500(db_session, setup):
    _, _, n = setup()
    responses.post(URL, status=500)
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is False
    assert n.delivery_error == "HTTP 500"


@responses.activate
def test_connection_error_truncated(db_session, setup):
    _, _, n = setup()
    responses.post(URL, body=requests.ConnectionError("x" * 900))
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is False
    assert n.delivery_error.startswith("ConnectionError: xxx")
    assert len(n.delivery_error) <= 500


@responses.activate
def test_timeout_passed(db_session, setup):
    _, _, n = setup()
    responses.post(URL, status=204)
    webhooks.deliver_notifications(db_session, [n.id])
    assert responses.calls[0].request.req_kwargs["timeout"] == 5
    db_session.refresh(n)
    assert n.delivered is True


@responses.activate
def test_timeout_error_recorded(db_session, setup):
    _, _, n = setup()
    responses.post(URL, body=requests.Timeout("slow"))
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivery_error == "Timeout: slow"


@responses.activate
def test_no_webhook_untouched(db_session, setup):
    _, _, n = setup(webhook_url=None)
    webhooks.deliver_notifications(db_session, [n.id])
    assert len(responses.calls) == 0
    db_session.refresh(n)
    assert n.delivered is False and n.delivery_error is None


def test_never_raises(db_session, setup, monkeypatch):
    _, _, n = setup()

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhooks._session, "post", boom)
    webhooks.deliver_notifications(db_session, [n.id, 999999])
