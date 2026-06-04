"""Add product_name column to reviews."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column("product_name", sa.String(length=512), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE reviews r
        SET product_name = COALESCE(NULLIF(p.name, ''), NULLIF(p.slug, ''), '')
        FROM products p
        WHERE r.product_id = p.id
        """
    )


def downgrade() -> None:
    op.drop_column("reviews", "product_name")
