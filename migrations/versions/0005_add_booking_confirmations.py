"""Record what each dispatcher was asked to confirm, so the server can enforce the yes.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_confirmations",
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.issue_id"), primary_key=True),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), sa.ForeignKey("maintenance_shops.shop_id"), nullable=False),
        sa.Column("estimate", sa.Numeric(10, 2), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("booking_confirmations")
