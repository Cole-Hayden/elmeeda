"""Add trucks, shops, and bookings, and issue details.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trucks",
        sa.Column("truck_id", sa.Uuid(), primary_key=True),
        sa.Column("unit_number", sa.String(32), nullable=False, unique=True),
        sa.Column("make", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
    )

    # Every new issue column is nullable, so existing issues remain valid.
    op.add_column("issues", sa.Column("truck_id", sa.Uuid(), nullable=True))
    op.add_column("issues", sa.Column("problem", sa.String(32), nullable=True))
    op.add_column("issues", sa.Column("location_description", sa.String(255), nullable=True))
    op.add_column("issues", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("issues", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("issues", sa.Column("drivable", sa.Boolean(), nullable=True))
    op.add_column("issues", sa.Column("needed_by", sa.Date(), nullable=True))
    op.add_column("issues", sa.Column("max_distance_miles", sa.Float(), nullable=True))
    op.add_column("issues", sa.Column("max_budget", sa.Numeric(10, 2), nullable=True))
    op.create_foreign_key("issues_truck_id_fkey", "issues", "trucks", ["truck_id"], ["truck_id"])

    op.create_table(
        "maintenance_shops",
        sa.Column("shop_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_description", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("open_bays", sa.Integer(), nullable=False),
        sa.Column("earliest_start", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("open_bays >= 0", name="ck_shops_open_bays_not_negative"),
    )

    op.create_table(
        "shop_estimates",
        sa.Column(
            "shop_id",
            sa.Uuid(),
            sa.ForeignKey("maintenance_shops.shop_id"),
            primary_key=True,
        ),
        sa.Column("problem", sa.String(32), primary_key=True),
        sa.Column("estimate", sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        "bookings",
        sa.Column("booking_id", sa.String(16), primary_key=True),
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.issue_id"), nullable=False),
        sa.Column(
            "shop_id",
            sa.Uuid(),
            sa.ForeignKey("maintenance_shops.shop_id"),
            nullable=False,
        ),
        sa.Column("estimate", sa.Numeric(10, 2), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issue_id"),
    )


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("shop_estimates")
    op.drop_table("maintenance_shops")
    op.drop_constraint("issues_truck_id_fkey", "issues", type_="foreignkey")
    op.drop_column("issues", "max_budget")
    op.drop_column("issues", "max_distance_miles")
    op.drop_column("issues", "needed_by")
    op.drop_column("issues", "drivable")
    op.drop_column("issues", "longitude")
    op.drop_column("issues", "latitude")
    op.drop_column("issues", "location_description")
    op.drop_column("issues", "problem")
    op.drop_column("issues", "truck_id")
    op.drop_table("trucks")
