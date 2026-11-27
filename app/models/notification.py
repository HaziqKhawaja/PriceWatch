from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.watch import Watch


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (CheckConstraint("type IN ('price_drop', 'restock')", name="type"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    delivery_error: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    watch: Mapped["Watch"] = relationship(back_populates="notifications")
