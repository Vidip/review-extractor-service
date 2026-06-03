"""Add review body and author columns to reviews."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("review", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("review_title", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("review_author", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("review_author_job_title", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "review_author_job_title")
    op.drop_column("reviews", "review_author")
    op.drop_column("reviews", "review_title")
    op.drop_column("reviews", "review")
