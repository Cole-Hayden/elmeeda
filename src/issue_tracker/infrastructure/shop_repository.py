from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.infrastructure.models import LOCAL_TIME_ZONE, MaintenanceShopModel


def shop_from_model(model: MaintenanceShopModel) -> MaintenanceShop:
    return MaintenanceShop(
        shop_id=model.shop_id,
        name=model.name,
        location=Location(model.location_description, model.latitude, model.longitude),
        open_bays=model.open_bays,
        earliest_start=model.earliest_start.astimezone(LOCAL_TIME_ZONE),
        estimates={ProblemType(row.problem): row.estimate for row in model.estimates},
    )


class SqlAlchemyMaintenanceShopRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_all(self) -> list[MaintenanceShop]:
        try:
            async with self._session_factory() as session:
                models = await session.scalars(
                    select(MaintenanceShopModel).order_by(MaintenanceShopModel.name)
                )
                return [shop_from_model(model) for model in models]
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
