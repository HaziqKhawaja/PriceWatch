from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.price_snapshot import PriceSnapshot
    from app.models.retailer import Retailer
    from app.models.watch import Watch


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    retailer_id: Mapped[int] = mapped_column(ForeignKey("retailers.id"))
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    retailer: Mapped["Retailer"] = relationship(back_populates="products")
    snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )
    watches: Mapped[list["Watch"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )
