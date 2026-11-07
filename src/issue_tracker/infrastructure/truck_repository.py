from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.truck import Truck
from issue_tracker.infrastructure.models import TruckModel


def truck_from_model(model: TruckModel) -> Truck:
    return Truck(
        truck_id=model.truck_id,
        unit_number=model.unit_number,
        make=model.make,
        model=model.model,
        year=model.year,
        vin=model.vin,
        engine=model.engine,
    )


class SqlAlchemyTruckRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, truck_id: UUID) -> Truck | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(TruckModel, truck_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return truck_from_model(model) if model else None

    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        try:
            async with self._session_factory() as session:
                model = await session.scalar(
                    select(TruckModel).where(TruckModel.unit_number == unit_number)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return truck_from_model(model) if model else None
