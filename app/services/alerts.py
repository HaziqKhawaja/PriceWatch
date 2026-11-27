from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, PriceSnapshot, Product, Watch


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def evaluate_watches(
    db: Session, product: Product, previous: PriceSnapshot | None, current: PriceSnapshot
) -> list[int]:
    """Create Notification rows for active watches and flush; return their ids.

    Does not commit and does no network I/O.
    """
    watches = db.scalars(
        select(Watch)
        .where(Watch.product_id == product.id, Watch.active.is_(True))
        .order_by(Watch.id)
    ).all()
    price = current.price
    notifications: list[Notification] = []
    for watch in watches:
        target = watch.target_price
        if target is not None:
            if price <= target:
                if not watch.price_alert_active:
                    watch.price_alert_active = True
                    notifications.append(
                        Notification(
                            watch_id=watch.id,
                            type="price_drop",
                            message=(
                                f"Price dropped to {_money(price)} "
                                f"(target {_money(target)}): {product.title}"
                            ),
                            price=price,
                        )
                    )
            else:
                watch.price_alert_active = False
        if (
            watch.notify_on_restock
            and previous is not None
            and previous.in_stock is False
            and current.in_stock is True
        ):
            notifications.append(
                Notification(
                    watch_id=watch.id,
                    type="restock",
                    message=f"Back in stock at {_money(price)}: {product.title}",
                    price=price,
                )
            )
    db.add_all(notifications)
    db.flush()
    return [n.id for n in notifications]
