from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Identity, Integer, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text, unique=True)
    scraper_key: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    rate_limit_seconds: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    products: Mapped[list["Product"]] = relationship(back_populates="retailer")
