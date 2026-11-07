from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import (
    BookingRejectedError,
    BookingRejection,
    StorageUnavailableError,
)
from issue_tracker.domain.booking import Booking
from issue_tracker.infrastructure.issue_repository import issue_from_model
from issue_tracker.infrastructure.models import (
    LOCAL_TIME_ZONE,
    BookingModel,
    IssueModel,
    MaintenanceShopModel,
)
from issue_tracker.infrastructure.shop_repository import shop_from_model


def booking_from_model(model: BookingModel) -> Booking:
    return Booking(
        booking_id=model.booking_id,
        issue_id=model.issue_id,
        shop_id=model.shop_id,
        estimate=model.estimate,
        start_time=model.start_time.astimezone(LOCAL_TIME_ZONE),
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

    @staticmethod
    async def _add_in_transaction(session: AsyncSession, booking: Booking) -> Booking:
        # Locks are always taken issue first, then shop, so bookings can't deadlock. The issue
        # lock makes retries for one breakdown wait their turn; the shop lock does the same for
        # calls competing over its last bay.
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
        if issue.problem is None or issue.missing_details():
            raise BookingRejectedError(BookingRejection.ISSUE_INCOMPLETE)

        shop_model = await session.scalar(
            select(MaintenanceShopModel)
            .where(MaintenanceShopModel.shop_id == booking.shop_id)
            .with_for_update()
        )
        if shop_model is None:
            raise BookingRejectedError(BookingRejection.SHOP_NOT_FOUND)

        shop = shop_from_model(shop_model)
        if shop.open_bays < 1:
            raise BookingRejectedError(BookingRejection.NO_OPEN_BAY)
        if (
            shop.estimate_for(issue.problem) != booking.estimate
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
