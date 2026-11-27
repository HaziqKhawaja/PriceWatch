from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.product import Money, _check_url
from app.services import url_safety


def _check_outbound(value: str) -> str:
    # Module-attribute lookup at call time so tests can monkeypatch it.
    return url_safety.check_outbound_url(value)


TargetPrice = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
WebhookUrl = Annotated[str, AfterValidator(_check_url), AfterValidator(_check_outbound)]


class WatchProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    current_price: Money | None
    in_stock: bool | None


class WatchCreate(BaseModel):
    product_id: int
    target_price: TargetPrice | None = None
    notify_on_restock: bool = False
    webhook_url: WebhookUrl | None = None


class WatchUpdate(BaseModel):
    # Omitted fields are untouched; explicit null clears target_price / webhook_url.
    target_price: TargetPrice | None = None
    notify_on_restock: bool | None = None
    webhook_url: WebhookUrl | None = None
    active: bool | None = None


class WatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product: WatchProduct
    target_price: Money | None
    notify_on_restock: bool
    webhook_url: str | None
    active: bool
    price_alert_active: bool
    created_at: datetime
