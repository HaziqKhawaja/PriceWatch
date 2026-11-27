from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import PriceSnapshot, Product
from app.schemas.common import Page
from app.schemas.history import SnapshotRead, TrendsResponse
from app.services.analytics import TrendsResult, build_trends, snapshots_to_frame

router = APIRouter(prefix="/products", tags=["history"])

Days = Annotated[int, Query(ge=1, le=3650)]


def _require_product(db: DbSession, product_id: int) -> None:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


def _load_frame(db: DbSession, product_id: int):
    rows = db.execute(
        select(PriceSnapshot.scraped_at, PriceSnapshot.price, PriceSnapshot.in_stock)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(PriceSnapshot.scraped_at, PriceSnapshot.id)
    ).all()
    return snapshots_to_frame([tuple(r) for r in rows])


def _series_records(result: TrendsResult) -> list[dict]:
    series = result.series.copy()
    series["date"] = series["date"].map(lambda d: d.isoformat())
    return series.to_dict("records")


@router.get("/{product_id}/history", response_model=Page[SnapshotRead])
def get_history(
    product_id: int,
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_product(db, product_id)
    where = PriceSnapshot.product_id == product_id
    total = db.scalar(select(func.count()).select_from(PriceSnapshot).where(where)) or 0
    items = db.scalars(
        select(PriceSnapshot)
        .where(where)
        .order_by(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[SnapshotRead](items=items, total=total, limit=limit, offset=offset)


@router.get("/{product_id}/trends", response_model=TrendsResponse)
def get_trends(
    product_id: int,
    db: DbSession,
    user: CurrentUser,
    days: Days = 90,
    include_outliers: bool = False,
):
    _require_product(db, product_id)
    result = build_trends(_load_frame(db, product_id), days, include_outliers)
    return TrendsResponse(
        product_id=product_id,
        days=days,
        include_outliers=include_outliers,
        series=_series_records(result),
        stats=result.stats,
    )


@router.get("/{product_id}/history.csv")
def export_history_csv(
    product_id: int,
    db: DbSession,
    user: CurrentUser,
    days: Days | None = None,
    normalized: bool = False,
    include_outliers: bool = False,
):
    _require_product(db, product_id)
    history = _load_frame(db, product_id)
    if normalized:
        out = build_trends(history, days or 90, include_outliers).series
        suffix = "-normalized"
    else:
        out = history
        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            out = out[out["scraped_at"] >= cutoff]
        out = out.copy()
        out["scraped_at"] = out["scraped_at"].map(lambda t: t.isoformat(timespec="seconds"))
        out["price"] = out["price"].map(lambda p: f"{p:.2f}")
        suffix = ""
    filename = f"product-{product_id}-history{suffix}.csv"
    return Response(
        content=out.to_csv(index=False, float_format="%.2f"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
