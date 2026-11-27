from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.notification import Notification
    from app.models.product import Product
    from app.models.user import User


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notify_on_restock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    price_alert_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    webhook_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="watches")
    product: Mapped["Product"] = relationship(back_populates="watches")
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="watch", cascade="all, delete-orphan", passive_deletes=True
    )
