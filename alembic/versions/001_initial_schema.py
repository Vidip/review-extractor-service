"""Initial schema: products, reviews, sync_runs with pgvector."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

sync_status = postgresql.ENUM(
    "pending", "syncing", "ready", "error",
    name="sync_status",
    create_type=False,
)
sync_mode = postgresql.ENUM(
    "full", "incremental",
    name="sync_mode",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    sync_status.create(op.get_bind(), checkfirst=True)
    sync_mode.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("capterra_url", sa.String(length=2048), nullable=False),
        sa.Column("slug", sa.String(length=512), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("sync_status", sync_status, nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_review_date", sa.Date(), nullable=True),
        sa.Column("known_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pagination_total_pages", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capterra_url"),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("mode", sync_mode, nullable=False),
        sa.Column("pages_crawled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_reviews", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("pros", sa.Text(), nullable=False),
        sa.Column("cons", sa.Text(), nullable=False),
        sa.Column("emotion", sa.String(length=256), nullable=False),
        sa.Column("rating", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "content_hash", name="uq_reviews_product_hash"),
    )
    op.create_index("ix_reviews_product_date", "reviews", ["product_id", "review_date"])


def downgrade() -> None:
    op.drop_index("ix_reviews_product_date", table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("sync_runs")
    op.drop_table("products")
    op.execute("DROP TYPE IF EXISTS sync_mode")
    op.execute("DROP TYPE IF EXISTS sync_status")
