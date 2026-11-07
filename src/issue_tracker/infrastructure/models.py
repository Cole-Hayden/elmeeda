from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
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


class MaintenanceShopModel(Base):
    __tablename__ = "maintenance_shops"
    __table_args__ = (CheckConstraint("open_bays >= 0", name="ck_shops_open_bays_not_negative"),)

    shop_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    location_description: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float]
    longitude: Mapped[float]
    open_bays: Mapped[int]
    earliest_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Loaded eagerly because lazy loading isn't available on an async session.
    estimates: Mapped[list[ShopEstimateModel]] = relationship(lazy="selectin")


class ShopEstimateModel(Base):
    __tablename__ = "shop_estimates"

    shop_id: Mapped[UUID] = mapped_column(
        ForeignKey("maintenance_shops.shop_id"), primary_key=True
    )
    problem: Mapped[str] = mapped_column(String(32), primary_key=True)
    estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class BookingModel(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Unique so that the database itself refuses to book one breakdown twice.
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.issue_id"), unique=True)
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("maintenance_shops.shop_id"))
    estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
