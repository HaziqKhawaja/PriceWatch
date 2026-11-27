import logging
from datetime import UTC

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, PriceSnapshot

USER_AGENT = "PriceWatch/0.1 (+mock)"
TIMEOUT_SECONDS = 5
ERROR_LIMIT = 500

logger = logging.getLogger(__name__)

_session = requests.Session()
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
                response = _session.post(
                    url, json=_payload(db, notification), timeout=TIMEOUT_SECONDS
                )
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
