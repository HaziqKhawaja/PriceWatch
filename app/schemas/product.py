from datetime import datetime
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer

Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str)]


def _check_url(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        raise ValueError("Invalid URL") from None
    if parts.scheme.lower() not in ("http", "https") or not host:
        raise ValueError("URL must be an absolute http(s) URL")
    return value


class ProductCreate(BaseModel):
    url: Annotated[str, AfterValidator(_check_url)]


class RetailerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str


class WatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_price: Money | None
    notify_on_restock: bool
    active: bool


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    retailer: RetailerRead
    url: str
    title: str
    external_id: str | None
    current_price: Money | None
    in_stock: bool | None
    last_scraped_at: datetime | None
    created_at: datetime


class ProductWithWatch(ProductRead):
    watch: WatchSummary
