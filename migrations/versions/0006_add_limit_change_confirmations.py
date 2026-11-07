"""Record loosened limits awaiting a yes, so the model can't loosen one by itself.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "limit_change_confirmations",
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.issue_id"), primary_key=True),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("max_distance_miles", sa.Float(), nullable=True),
        sa.Column("needed_by", sa.Date(), nullable=True),
        sa.Column("max_budget", sa.Numeric(10, 2), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("limit_change_confirmations")
