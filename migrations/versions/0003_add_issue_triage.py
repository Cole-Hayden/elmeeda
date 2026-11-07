"""Add the job catalog, vendor capabilities, tow service, and new issue details.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trucks", sa.Column("vin", sa.String(17), nullable=True))
    op.add_column("trucks", sa.Column("engine", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_trucks_vin", "trucks", ["vin"])

    op.add_column("issues", sa.Column("symptoms", sa.Text(), nullable=True))
    op.add_column("issues", sa.Column("contact_name", sa.String(255), nullable=True))
    op.add_column("issues", sa.Column("contact_phone", sa.String(32), nullable=True))
    op.add_column("issues", sa.Column("loaded", sa.Boolean(), nullable=True))
    op.add_column("issues", sa.Column("hazmat", sa.Boolean(), nullable=True))
    op.add_column("issues", sa.Column("odometer_miles", sa.Integer(), nullable=True))
    op.add_column(
        "issues",
        sa.Column(
            "fault_codes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("issues", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_issues_idempotency_key", "issues", ["idempotency_key"])

    op.add_column(
        "maintenance_shops", sa.Column("tow_base_fee", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "maintenance_shops", sa.Column("tow_per_mile", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "maintenance_shops",
        sa.Column("tows_hazmat", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_shops_tow_fees_set_together",
        "maintenance_shops",
        "(tow_base_fee IS NULL) = (tow_per_mile IS NULL)",
    )

    op.create_table(
        "jobs",
        sa.Column("job_code", sa.String(64), primary_key=True),
        sa.Column("problem", sa.String(32), nullable=False),
        sa.Column("make", sa.String(64), nullable=True),
        sa.Column("engine", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("labor_hours", sa.Numeric(5, 1), nullable=False),
        sa.Column("requires_diagnosis", sa.Boolean(), nullable=False),
        sa.Column("vmrs_code", sa.String(16), nullable=True),
        sa.UniqueConstraint(
            "problem",
            "make",
            "engine",
            name="uq_jobs_variant",
            postgresql_nulls_not_distinct=True,
        ),
    )

    op.create_table(
        "job_parts",
        sa.Column("job_code", sa.String(64), sa.ForeignKey("jobs.job_code"), primary_key=True),
        sa.Column("part_number", sa.String(64), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_job_parts_quantity_positive"),
    )

    op.create_table(
        "vendor_capabilities",
        sa.Column(
            "shop_id",
            sa.Uuid(),
            sa.ForeignKey("maintenance_shops.shop_id"),
            primary_key=True,
        ),
        sa.Column("job_code", sa.String(64), sa.ForeignKey("jobs.job_code"), primary_key=True),
        sa.Column("labor_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("authorized_makes", postgresql.ARRAY(sa.String(64)), nullable=True),
    )

    # Not converted to capabilities, because this table only holds mock data the seed recreates.
    op.drop_table("shop_estimates")


def downgrade() -> None:
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
    op.drop_table("vendor_capabilities")
    op.drop_table("job_parts")
    op.drop_table("jobs")

    op.drop_constraint("ck_shops_tow_fees_set_together", "maintenance_shops", type_="check")
    op.drop_column("maintenance_shops", "tows_hazmat")
    op.drop_column("maintenance_shops", "tow_per_mile")
    op.drop_column("maintenance_shops", "tow_base_fee")

    op.drop_constraint("uq_issues_idempotency_key", "issues", type_="unique")
    op.drop_column("issues", "idempotency_key")
    op.drop_column("issues", "fault_codes")
    op.drop_column("issues", "odometer_miles")
    op.drop_column("issues", "hazmat")
    op.drop_column("issues", "loaded")
    op.drop_column("issues", "contact_phone")
    op.drop_column("issues", "contact_name")
    op.drop_column("issues", "symptoms")

    op.drop_constraint("uq_trucks_vin", "trucks", type_="unique")
    op.drop_column("trucks", "engine")
    op.drop_column("trucks", "vin")
