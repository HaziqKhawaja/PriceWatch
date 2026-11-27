from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Index, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.product import Product


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index("ix_price_snapshots_product_id_scraped_at", "product_id", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    in_stock: Mapped[bool] = mapped_column(Boolean)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="snapshots")
