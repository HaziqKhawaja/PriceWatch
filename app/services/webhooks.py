import logging
import socket
from datetime import UTC

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib3 import connection as urllib3_connection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.connection import create_connection

from app.models import Notification, PriceSnapshot
from app.services import url_safety

USER_AGENT = "PriceWatch/0.1 (+mock)"
TIMEOUT_SECONDS = 5
ERROR_LIMIT = 500

logger = logging.getLogger(__name__)


class BlockedConnectionError(OSError):
    """Connection refused by the SSRF guard (surfaces as requests.ConnectionError)."""


class _PinnedMixin:
    """Connect to the IP vetted at connection time, never to a fresh DNS answer."""

    def _new_conn(self) -> socket.socket:
        try:
            ip = url_safety.pick_connect_ip(self._dns_host, self.port)
        except url_safety.UnsafeURLError as exc:
            raise BlockedConnectionError(f"Blocked: {exc}") from None
        if ip is None:
            return super()._new_conn()
        try:
            return create_connection(
                (ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except TimeoutError as exc:
            raise urllib3_connection.ConnectTimeoutError(
                self, f"Connection to {self.host} timed out. (connect timeout={self.timeout})"
            ) from exc
        except OSError as exc:
            raise urllib3_connection.NewConnectionError(
                self, f"Failed to establish a new connection: {exc}"
            ) from exc


class _PinnedHTTPConnection(_PinnedMixin, urllib3_connection.HTTPConnection):
    pass


class _PinnedHTTPSConnection(_PinnedMixin, urllib3_connection.HTTPSConnection):
    pass


class _PinnedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class PinnedAdapter(HTTPAdapter):
    """HTTPAdapter whose urllib3 pools use IP-pinning connections (send() is untouched)."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _PinnedHTTPPool,
            "https": _PinnedHTTPSPool,
        }


_session = requests.Session()
_session.trust_env = False
_session.mount("http://", PinnedAdapter())
_session.mount("https://", PinnedAdapter())
_session.headers["User-Agent"] = USER_AGENT
_session.headers["Content-Type"] = "application/json"


def _float(value) -> float | None:
    return None if value is None else float(value)


def _payload(db: Session, notification: Notification) -> dict:
    watch = notification.watch
    product = watch.product
    # Delivery runs right after the snapshot commit, so the latest snapshot is the
    # current one and the one before it is the previous one.
    previous_price = db.scalar(
        select(PriceSnapshot.price)
        .where(PriceSnapshot.product_id == product.id)
        .order_by(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())
        .offset(1)
        .limit(1)
    )
    created = notification.created_at
    triggered_at = created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": notification.type,
        "notification_id": notification.id,
        "watch_id": watch.id,
        "product": {
            "id": product.id,
            "title": product.title,
            "url": product.url,
            "retailer": product.retailer.name,
        },
        "price": _float(notification.price),
        "target_price": _float(watch.target_price),
        "previous_price": _float(previous_price),
        "in_stock": product.in_stock,
        "currency": "USD",
        "triggered_at": triggered_at,
    }


def _truncate(message: str) -> str:
    return message[:ERROR_LIMIT]


def deliver_notifications(db: Session, notification_ids: list[int]) -> None:
    """POST each notification to its watch's webhook_url. Never raises for delivery failures."""
    for notification_id in notification_ids:
        try:
            notification = db.get(Notification, notification_id)
            if notification is None or not notification.watch.webhook_url:
                continue
            url = notification.watch.webhook_url
            try:
                try:
                    url_safety.check_outbound_url(url)
                except url_safety.UnsafeURLError as exc:
                    notification.delivered = False
                    notification.delivery_error = _truncate(f"Blocked: {exc}")
                    continue
                response = _session.post(
                    url,
                    json=_payload(db, notification),
                    timeout=TIMEOUT_SECONDS,
                    allow_redirects=False,
                    stream=True,  # status only; never download the receiver's body
                )
                response.close()
                if 200 <= response.status_code < 300:
                    notification.delivered = True
                    notification.delivery_error = None
                else:
                    notification.delivered = False
                    notification.delivery_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                notification.delivered = False
                notification.delivery_error = _truncate(f"{type(exc).__name__}: {exc}")
        except Exception:
            logger.exception("Webhook delivery failed for notification %s", notification_id)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record webhook delivery results")
