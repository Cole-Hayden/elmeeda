from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import (
    BookingRejectedError,
    BookingRejection,
    StorageUnavailableError,
)
from issue_tracker.domain.booking import BookedRepair, Booking
from issue_tracker.domain.job import select_job
from issue_tracker.domain.vendor_matching import calculate_quote, check_capability, check_tow
from issue_tracker.infrastructure.issue_repository import issue_from_model
from issue_tracker.infrastructure.job_repository import job_from_model
from issue_tracker.infrastructure.models import (
    LOCAL_TIME_ZONE,
    BookingModel,
    IssueModel,
    JobModel,
    MaintenanceShopModel,
    TruckModel,
)
from issue_tracker.infrastructure.shop_repository import shop_from_model
from issue_tracker.infrastructure.truck_repository import truck_from_model


def booking_from_model(model: BookingModel) -> Booking:
    return Booking(
        booking_id=model.booking_id,
        issue_id=model.issue_id,
        shop_id=model.shop_id,
        estimate=model.estimate,
        start_time=model.start_time.astimezone(LOCAL_TIME_ZONE),
    )


def _truck_booking(truck_id: UUID) -> Select[BookingModel]:
    return (
        select(BookingModel)
        .join(IssueModel, BookingModel.issue_id == IssueModel.issue_id)
        .where(IssueModel.truck_id == truck_id)
    )


class SqlAlchemyBookingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, booking: Booking) -> Booking:
        try:
            async with self._session_factory.begin() as session:
                return await self._add_in_transaction(session, booking)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get(self, booking_id: str) -> Booking | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(BookingModel, booking_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return booking_from_model(model) if model else None

    async def get_for_issue(self, issue_id: UUID) -> Booking | None:
        try:
            async with self._session_factory() as session:
                model = await session.scalar(
                    select(BookingModel).where(BookingModel.issue_id == issue_id)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return booking_from_model(model) if model else None

    async def get_for_truck(self, truck_id: UUID) -> Booking | None:
        try:
            async with self._session_factory() as session:
                model = await session.scalar(_truck_booking(truck_id))
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return booking_from_model(model) if model else None

    async def list_booked_repairs(self) -> list[BookedRepair]:
        statement = (
            select(BookingModel, IssueModel, TruckModel.unit_number, MaintenanceShopModel.name)
            .join(IssueModel, BookingModel.issue_id == IssueModel.issue_id)
            .join(TruckModel, IssueModel.truck_id == TruckModel.truck_id)
            .join(MaintenanceShopModel, BookingModel.shop_id == MaintenanceShopModel.shop_id)
            .order_by(IssueModel.created_at.desc(), BookingModel.booking_id)
        )
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(statement)).all()
                repairs = []
                for booking, issue_model, unit_number, shop_name in rows:
                    issue = issue_from_model(issue_model)
                    repairs.append(
                        BookedRepair(
                            booking=booking_from_model(booking),
                            truck_unit_number=unit_number,
                            problem=issue.problem.value if issue.problem else None,
                            location=issue.location.description if issue.location else None,
                            shop_name=shop_name,
                        )
                    )
                return repairs
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    @staticmethod
    async def _add_in_transaction(session: AsyncSession, booking: Booking) -> Booking:
        # Locks are always taken issue, then truck, then shop, so bookings can't deadlock. The
        # issue lock makes retries for one breakdown wait their turn. The truck lock does the
        # same across calls, because each call creates its own issue. The shop lock does the
        # same for calls competing over its last bay.
        issue_model = await session.scalar(
            select(IssueModel).where(IssueModel.issue_id == booking.issue_id).with_for_update()
        )
        if issue_model is None:
            raise BookingRejectedError(BookingRejection.ISSUE_NOT_FOUND)

        existing = await session.scalar(
            select(BookingModel).where(BookingModel.issue_id == booking.issue_id)
        )
        if existing is not None:
            if existing.shop_id == booking.shop_id:
                return booking_from_model(existing)
            raise BookingRejectedError(BookingRejection.ISSUE_ALREADY_BOOKED)

        issue = issue_from_model(issue_model)
        truck_model = (
            await session.scalar(
                select(TruckModel).where(TruckModel.truck_id == issue.truck_id).with_for_update()
            )
            if issue.truck_id
            else None
        )
        if (
            issue.problem is None
            or issue.needed_by is None
            or truck_model is None
            or issue.missing_details()
        ):
            raise BookingRejectedError(BookingRejection.ISSUE_INCOMPLETE)
        if await session.scalar(_truck_booking(truck_model.truck_id)) is not None:
            raise BookingRejectedError(BookingRejection.TRUCK_ALREADY_BOOKED)

        shop_model = await session.scalar(
            select(MaintenanceShopModel)
            .where(MaintenanceShopModel.shop_id == booking.shop_id)
            .with_for_update()
        )
        if shop_model is None:
            raise BookingRejectedError(BookingRejection.SHOP_NOT_FOUND)

        shop = shop_from_model(shop_model)
        truck = truck_from_model(truck_model)
        job_models = await session.scalars(
            select(JobModel).where(JobModel.problem == issue.problem.value)
        )
        job = select_job((job_from_model(model) for model in job_models), issue.problem, truck)
        capability = shop.capability_for(job.job_code) if job else None
        if job is None or capability is None or check_capability(job, truck, shop):
            raise BookingRejectedError(BookingRejection.JOB_NOT_OFFERED)
        if shop.open_bays < 1:
            raise BookingRejectedError(BookingRejection.NO_OPEN_BAY)
        if (
            check_tow(issue, shop)
            or calculate_quote(issue, job, capability, shop).estimate != booking.estimate
            or shop.earliest_start != booking.start_time
        ):
            raise BookingRejectedError(BookingRejection.QUOTE_CHANGED)

        shop_model.open_bays -= 1
        session.add(
            BookingModel(
                booking_id=booking.booking_id,
                issue_id=booking.issue_id,
                shop_id=booking.shop_id,
                estimate=booking.estimate,
                start_time=booking.start_time,
            )
        )
        return booking
