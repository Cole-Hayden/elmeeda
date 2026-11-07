from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Postgres returns timestamps in UTC. Every mock shop is in Illinois, so times are converted
# back to Central on read. Otherwise the agent would read a 3:30 PM start as 9:30 PM.
LOCAL_TIME_ZONE = ZoneInfo("America/Chicago")


class Base(DeclarativeBase):
    pass


class TruckModel(Base):
    __tablename__ = "trucks"

    truck_id: Mapped[UUID] = mapped_column(primary_key=True)
    unit_number: Mapped[str] = mapped_column(String(32), unique=True)
    make: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    year: Mapped[int]
    vin: Mapped[str | None] = mapped_column(String(17), unique=True)
    engine: Mapped[str | None] = mapped_column(String(64))


class IssueModel(Base):
    __tablename__ = "issues"

    issue_id: Mapped[UUID] = mapped_column(primary_key=True)
    truck_id: Mapped[UUID | None] = mapped_column(ForeignKey("trucks.truck_id"))
    problem: Mapped[str | None] = mapped_column(String(32))
    location_description: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    drivable: Mapped[bool | None]
    needed_by: Mapped[date | None]
    max_distance_miles: Mapped[float | None]
    max_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    symptoms: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    loaded: Mapped[bool | None]
    hazmat: Mapped[bool | None]
    odometer_miles: Mapped[int | None]
    fault_codes: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "problem",
            "make",
            "engine",
            name="uq_jobs_variant",
            postgresql_nulls_not_distinct=True,
        ),
    )

    job_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    problem: Mapped[str] = mapped_column(String(32))
    make: Mapped[str | None] = mapped_column(String(64))
    engine: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    labor_hours: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    requires_diagnosis: Mapped[bool]
    vmrs_code: Mapped[str | None] = mapped_column(String(16))

    # Loaded eagerly because lazy loading isn't available on an async session.
    parts: Mapped[list[JobPartModel]] = relationship(
        lazy="selectin", order_by="JobPartModel.part_number"
    )


class JobPartModel(Base):
    __tablename__ = "job_parts"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_job_parts_quantity_positive"),)

    job_code: Mapped[str] = mapped_column(ForeignKey("jobs.job_code"), primary_key=True)
    part_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class MaintenanceShopModel(Base):
    __tablename__ = "maintenance_shops"
    __table_args__ = (
        CheckConstraint("open_bays >= 0", name="ck_shops_open_bays_not_negative"),
        CheckConstraint(
            "(tow_base_fee IS NULL) = (tow_per_mile IS NULL)",
            name="ck_shops_tow_fees_set_together",
        ),
    )

    shop_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    location_description: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float]
    longitude: Mapped[float]
    open_bays: Mapped[int]
    earliest_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tow_base_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    tow_per_mile: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    tows_hazmat: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    # Loaded eagerly because lazy loading isn't available on an async session.
    capabilities: Mapped[list[VendorCapabilityModel]] = relationship(lazy="selectin")


class VendorCapabilityModel(Base):
    __tablename__ = "vendor_capabilities"

    shop_id: Mapped[UUID] = mapped_column(
        ForeignKey("maintenance_shops.shop_id"), primary_key=True
    )
    job_code: Mapped[str] = mapped_column(ForeignKey("jobs.job_code"), primary_key=True)
    labor_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    authorized_makes: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))


class BookingModel(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Unique so that the database itself refuses to book one breakdown twice.
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.issue_id"), unique=True)
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("maintenance_shops.shop_id"))
    estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
