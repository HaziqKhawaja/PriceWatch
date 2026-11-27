from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.product import Money


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scraped_at: datetime
    price: Money
    in_stock: bool


class TrendPoint(BaseModel):
    date: str
    price: float
    ma_7: float
    ma_30: float
    in_stock: bool


class TrendStats(BaseModel):
    current: float | None = None
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    pct_change: float | None = None
    is_all_time_low: bool | None = None
    vs_30d_avg_pct: float | None = None


class TrendsResponse(BaseModel):
    product_id: int
    days: int
    include_outliers: bool
    series: list[TrendPoint]
    stats: TrendStats
