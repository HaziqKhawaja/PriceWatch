from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.models import Product, Watch
from app.schemas.common import Page
from app.schemas.watch import WatchCreate, WatchRead, WatchUpdate

router = APIRouter(prefix="/watches", tags=["watches"])


def _get_owned(db: DbSession, user: CurrentUser, watch_id: int) -> Watch:
    watch = db.scalar(select(Watch).where(Watch.id == watch_id, Watch.user_id == user.id))
    if watch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch not found")
    return watch


@router.get("", response_model=Page[WatchRead])
def list_watches(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(Watch).where(Watch.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Watch.id).limit(limit).offset(offset)).all()
    return Page[WatchRead](items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=WatchRead, status_code=status.HTTP_201_CREATED)
def create_watch(payload: WatchCreate, db: DbSession, user: CurrentUser):
    if db.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    conflict = HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Already watching this product"
    )
    if db.scalar(
        select(Watch.id).where(Watch.user_id == user.id, Watch.product_id == payload.product_id)
    ):
        raise conflict
    watch = Watch(user_id=user.id, **payload.model_dump())
    db.add(watch)
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate
        db.rollback()
        raise conflict from None
    db.refresh(watch)
    return watch


@router.patch("/{watch_id}", response_model=WatchRead)
def update_watch(watch_id: int, payload: WatchUpdate, db: DbSession, user: CurrentUser):
    watch = _get_owned(db, user, watch_id)
    data = payload.model_dump(exclude_unset=True)
    for field in ("notify_on_restock", "active"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "type": "none_not_allowed",
                        "loc": ["body", field],
                        "msg": "Input should be a valid boolean",
                        "input": None,
                    }
                ],
            )
    if "target_price" in data and data["target_price"] != watch.target_price:
        watch.price_alert_active = False
    for field, value in data.items():
        setattr(watch, field, value)
    db.commit()
    db.refresh(watch)
    return watch


@router.delete("/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(watch_id: int, db: DbSession, user: CurrentUser):
    db.delete(_get_owned(db, user, watch_id))
    db.commit()
