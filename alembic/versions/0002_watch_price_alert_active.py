"""add watches.price_alert_active

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watches",
        sa.Column(
            "price_alert_active", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("watches", "price_alert_active")
