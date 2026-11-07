from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.confirmation import LimitChange, PendingLimitChange
from issue_tracker.infrastructure.models import LimitChangeConfirmationModel


class SqlAlchemyLimitChangeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def prepare(self, pending: PendingLimitChange) -> None:
        values = {
            "confirmation_id": pending.confirmation_id,
            "max_distance_miles": pending.change.max_distance_miles,
            "needed_by": pending.change.needed_by,
            "max_budget": pending.change.max_budget,
            "confirmed": False,
        }
        statement = insert(LimitChangeConfirmationModel).values(issue_id=pending.issue_id, **values)
        try:
            async with self._session_factory.begin() as session:
                await session.execute(
                    statement.on_conflict_do_update(index_elements=["issue_id"], set_=values)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get(self, issue_id: UUID) -> PendingLimitChange | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(LimitChangeConfirmationModel, issue_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        if model is None:
            return None
        return PendingLimitChange(
            confirmation_id=model.confirmation_id,
            issue_id=model.issue_id,
            change=LimitChange(
                max_distance_miles=model.max_distance_miles,
                needed_by=model.needed_by,
                max_budget=model.max_budget,
            ),
            confirmed=model.confirmed,
        )

    async def record_answer(self, issue_id: UUID, confirmation_id: UUID, confirmed: bool) -> bool:
        try:
            async with self._session_factory.begin() as session:
                updated = await session.scalar(
                    update(LimitChangeConfirmationModel)
                    .where(
                        LimitChangeConfirmationModel.issue_id == issue_id,
                        LimitChangeConfirmationModel.confirmation_id == confirmation_id,
                    )
                    .values(confirmed=confirmed)
                    .returning(LimitChangeConfirmationModel.issue_id)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return updated is not None

    async def clear(self, issue_id: UUID) -> None:
        try:
            async with self._session_factory.begin() as session:
                await session.execute(
                    delete(LimitChangeConfirmationModel).where(
                        LimitChangeConfirmationModel.issue_id == issue_id
                    )
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
