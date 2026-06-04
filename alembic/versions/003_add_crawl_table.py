"""Add crawl singleton table for live fetch budget."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("crawl_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO crawl (id, crawl_count) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("crawl")
