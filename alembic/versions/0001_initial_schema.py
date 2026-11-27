"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        _created_at(),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "retailers",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("scraper_key", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("rate_limit_seconds", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retailers")),
        sa.UniqueConstraint("domain", name=op.f("uq_retailers_domain")),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("retailer_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("current_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["retailer_id"], ["retailers.id"], name=op.f("fk_products_retailer_id_retailers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("url", name=op.f("uq_products_url")),
    )
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=False),
        sa.Column(
            "scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_price_snapshots_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_snapshots")),
    )
    op.create_index(
        "ix_price_snapshots_product_id_scraped_at",
        "price_snapshots",
        ["product_id", "scraped_at"],
    )
    op.create_table(
        "watches",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("notify_on_restock", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_watches_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_watches_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watches")),
        sa.UniqueConstraint("user_id", "product_id", name=op.f("uq_watches_user_id_product_id")),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("watch_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        _created_at(),
        sa.Column("delivered", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('price_drop', 'restock')", name=op.f("ck_notifications_type")
        ),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["watches.id"],
            name=op.f("fk_notifications_watch_id_watches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("products_attempted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("succeeded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scrape_runs")),
    )


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("notifications")
    op.drop_table("watches")
    op.drop_index("ix_price_snapshots_product_id_scraped_at", table_name="price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_table("products")
    op.drop_table("retailers")
    op.drop_table("users")
