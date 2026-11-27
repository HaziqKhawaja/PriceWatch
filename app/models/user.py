from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Identity, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.watch import Watch


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="role"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="user", server_default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    watches: Mapped[list["Watch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
