from datetime import datetime

from sqlalchemy import DateTime, Identity, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products_attempted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    succeeded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text)
