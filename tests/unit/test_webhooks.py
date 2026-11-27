import json
import threading
from datetime import UTC
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests
import responses
from sqlalchemy import select

from app.config import get_settings
from app.models import Notification, PriceSnapshot, Product, Retailer, Watch
from app.services import url_safety, webhooks
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


def test_commit_failure_is_swallowed(db_session, monkeypatch):
    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    webhooks.deliver_notifications(db_session, [])


@responses.activate
def test_private_target_blocked_without_request(db_session, setup, fake_dns):
    fake_dns["internal.example"] = ["10.0.0.5"]
    _, _, n = setup(webhook_url="http://internal.example/in")
    responses.post("http://internal.example/in", status=200)
    webhooks.deliver_notifications(db_session, [n.id])
    assert len(responses.calls) == 0
    db_session.refresh(n)
    assert n.delivered is False
    assert n.delivery_error.startswith("Blocked:")


@responses.activate
def test_redirect_not_followed(db_session, setup):
    _, _, n = setup()
    responses.post(URL, status=302, headers={"Location": "http://169.254.169.254/"})
    webhooks.deliver_notifications(db_session, [n.id])
    assert len(responses.calls) == 1
    db_session.refresh(n)
    assert n.delivered is False
    assert n.delivery_error == "HTTP 302"


def test_session_ignores_env_proxies():
    assert webhooks._session.trust_env is False


class _Recorder(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.server.received.append((self.headers.get("Host"), self.rfile.read(length)))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def allow_hosts(monkeypatch):
    def set_hosts(value):
        monkeypatch.setenv("WEBHOOK_ALLOWED_HOSTS", value)
        get_settings.cache_clear()

    yield set_hosts
    monkeypatch.delenv("WEBHOOK_ALLOWED_HOSTS", raising=False)
    get_settings.cache_clear()


def test_rebinding_blocked_at_connection_layer(
    db_session, setup, fake_dns, local_server, monkeypatch
):
    port = local_server.server_address[1]
    # Pre-check passes (as if DNS answered with a public IP), then the name "rebinds".
    monkeypatch.setattr(url_safety, "check_outbound_url", lambda url: url)
    fake_dns["rebind.example"] = ["127.0.0.1"]
    _, _, n = setup(webhook_url=f"http://rebind.example:{port}/")
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert local_server.received == []
    assert n.delivered is False
    assert "Blocked:" in n.delivery_error


def test_allowlisted_host_connects_by_name(db_session, setup, local_server, allow_hosts):
    # "localhost" resolves via the real resolver inside the container (hosts file), no DNS.
    port = local_server.server_address[1]
    allow_hosts("localhost")
    _, _, n = setup(webhook_url=f"http://localhost:{port}/hook")
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is True, n.delivery_error
    assert len(local_server.received) == 1
    host, body = local_server.received[0]
    assert host == f"localhost:{port}"
    assert json.loads(body)["notification_id"] == n.id


def test_connection_uses_pinned_ip(db_session, setup, local_server, monkeypatch):
    port = local_server.server_address[1]
    monkeypatch.setattr(url_safety, "check_outbound_url", lambda url: url)
    seen = []

    def pick(host, p):
        seen.append((host, p))
        return "127.0.0.1"

    monkeypatch.setattr(url_safety, "pick_connect_ip", pick)
    _, _, n = setup(webhook_url=f"http://pinned.example:{port}/")
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is True, n.delivery_error
    assert seen == [("pinned.example", port)]
    assert [h for h, _ in local_server.received] == [f"pinned.example:{port}"]


def _closed_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_pinned_connection_refused_recorded(db_session, setup, monkeypatch):
    port = _closed_port()
    monkeypatch.setattr(url_safety, "check_outbound_url", lambda url: url)
    monkeypatch.setattr(url_safety, "pick_connect_ip", lambda host, p: "127.0.0.1")
    _, _, n = setup(webhook_url=f"http://pinned.example:{port}/")
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is False
    assert n.delivery_error.startswith("ConnectionError:")
    assert "Failed to establish a new connection" in n.delivery_error


def test_pinned_connect_timeout_recorded(db_session, setup, monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(url_safety, "check_outbound_url", lambda url: url)
    monkeypatch.setattr(url_safety, "pick_connect_ip", lambda host, p: "127.0.0.1")
    monkeypatch.setattr(webhooks, "create_connection", timeout)
    _, _, n = setup(webhook_url="http://pinned.example:9/")
    webhooks.deliver_notifications(db_session, [n.id])
    db_session.refresh(n)
    assert n.delivered is False
    assert "timed out" in n.delivery_error
