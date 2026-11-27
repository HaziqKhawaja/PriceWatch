from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Notification, Product, Watch
from app.schemas.common import Page
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])

_COLUMNS = (
    Notification.id,
    Notification.watch_id,
    Watch.product_id,
    Product.title.label("product_title"),
    Notification.type,
    Notification.message,
    Notification.price,
    Notification.created_at,
    Notification.delivered,
    Notification.delivery_error,
    Notification.read_at,
)


def _base(user_id: int):
    return (
        select(*_COLUMNS)
        .join(Watch, Notification.watch_id == Watch.id)
        .join(Product, Watch.product_id == Product.id)
        .where(Watch.user_id == user_id)
    )


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread: bool = False,
):
    query = _base(user.id)
    if unread:
        query = query.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [NotificationRead.model_validate(dict(r._mapping)) for r in rows]
    return Page[NotificationRead](items=items, total=total, limit=limit, offset=offset)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, db: DbSession, user: CurrentUser):
    owned = _base(user.id).where(Notification.id == notification_id)
    if db.execute(owned).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification = db.get(Notification, notification_id)
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
    return NotificationRead.model_validate(dict(db.execute(owned).one()._mapping))
