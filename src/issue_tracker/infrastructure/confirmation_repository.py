from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.confirmation import PreparedBooking
from issue_tracker.infrastructure.models import LOCAL_TIME_ZONE, BookingConfirmationModel


class SqlAlchemyConfirmationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def prepare(self, prepared: PreparedBooking) -> None:
        values = {
            "confirmation_id": prepared.confirmation_id,
            "shop_id": prepared.shop_id,
            "estimate": prepared.estimate,
            "start_time": prepared.start_time,
            "confirmed": False,
            "read_back": False,
        }
        statement = insert(BookingConfirmationModel).values(issue_id=prepared.issue_id, **values)
        try:
            async with self._session_factory.begin() as session:
                await session.execute(
                    statement.on_conflict_do_update(index_elements=["issue_id"], set_=values)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get(self, issue_id: UUID) -> PreparedBooking | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(BookingConfirmationModel, issue_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        if model is None:
            return None
        return PreparedBooking(
            confirmation_id=model.confirmation_id,
            issue_id=model.issue_id,
            shop_id=model.shop_id,
            estimate=model.estimate,
            start_time=model.start_time.astimezone(LOCAL_TIME_ZONE),
            confirmed=model.confirmed,
            read_back=model.read_back,
        )

    async def mark_read_back(self, issue_id: UUID, confirmation_id: UUID) -> None:
        try:
            async with self._session_factory.begin() as session:
                await session.execute(
                    update(BookingConfirmationModel)
                    .where(
                        BookingConfirmationModel.issue_id == issue_id,
                        BookingConfirmationModel.confirmation_id == confirmation_id,
                    )
                    .values(read_back=True)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def record_answer(self, issue_id: UUID, confirmation_id: UUID, confirmed: bool) -> bool:
        try:
            async with self._session_factory.begin() as session:
                updated = await session.scalar(
                    update(BookingConfirmationModel)
                    .where(
                        BookingConfirmationModel.issue_id == issue_id,
                        BookingConfirmationModel.confirmation_id == confirmation_id,
                    )
                    .values(confirmed=confirmed)
                    .returning(BookingConfirmationModel.issue_id)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return updated is not None

    async def clear(self, issue_id: UUID) -> None:
        try:
            async with self._session_factory.begin() as session:
                await session.execute(
                    delete(BookingConfirmationModel).where(
                        BookingConfirmationModel.issue_id == issue_id
                    )
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
