from datetime import datetime

from pydantic import BaseModel

from app.schemas.product import Money


class NotificationRead(BaseModel):
    id: int
    watch_id: int
    product_id: int
    product_title: str
    type: str
    message: str
    price: Money | None
    created_at: datetime
    delivered: bool
    delivery_error: str | None
    read_at: datetime | None
