from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Product, Retailer
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductRead, ProductWithWatch
from app.services.products import (
    ScrapeFailedError,
    UnsupportedRetailerError,
    add_product_for_user,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductWithWatch, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: DbSession, user: CurrentUser, response: Response):
    try:
        product, watch, created = add_product_for_user(db, user, payload.url)
    except UnsupportedRetailerError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except ScrapeFailedError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to scrape product"
        ) from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return ProductWithWatch.model_validate(
        {**ProductRead.model_validate(product).model_dump(), "watch": watch}
    )


@router.get("", response_model=Page[ProductRead])
def list_products(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    retailer: str | None = None,
    in_stock: bool | None = None,
):
    query = select(Product)
    if retailer is not None:
        if retailer.isdigit():
            query = query.where(Product.retailer_id == int(retailer))
        else:
            query = query.join(Retailer).where(func.lower(Retailer.name) == retailer.lower())
    if in_stock is not None:
        query = query.where(Product.in_stock.is_(in_stock))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Product.id).limit(limit).offset(offset)).all()
    return Page[ProductRead](items=items, total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession, user: CurrentUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product
