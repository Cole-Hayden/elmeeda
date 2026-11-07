"""Reset the mock data to the start of the scenario.

Run with `uv run python -m issue_tracker.infrastructure.seed`. This deletes all bookings,
trucks, shops, and any issue attached to a truck.
"""

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from issue_tracker.config import Settings
from issue_tracker.infrastructure.issue_repository import issue_to_model
from issue_tracker.infrastructure.mock_data import SCENARIO_ISSUE, SHOPS, TRUCKS
from issue_tracker.infrastructure.models import (
    BookingModel,
    IssueModel,
    MaintenanceShopModel,
    ShopEstimateModel,
    TruckModel,
)


async def reset_mock_data(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory.begin() as session:
        await session.execute(delete(BookingModel))
        await session.execute(delete(IssueModel).where(IssueModel.truck_id.is_not(None)))
        await session.execute(delete(ShopEstimateModel))
        await session.execute(delete(MaintenanceShopModel))
        await session.execute(delete(TruckModel))

        session.add_all(
            TruckModel(
                truck_id=truck.truck_id,
                unit_number=truck.unit_number,
                make=truck.make,
                model=truck.model,
                year=truck.year,
            )
            for truck in TRUCKS
        )
        session.add_all(
            MaintenanceShopModel(
                shop_id=shop.shop_id,
                name=shop.name,
                location_description=shop.location.description,
                latitude=shop.location.latitude,
                longitude=shop.location.longitude,
                open_bays=shop.open_bays,
                earliest_start=shop.earliest_start,
                estimates=[
                    ShopEstimateModel(problem=problem.value, estimate=estimate)
                    for problem, estimate in shop.estimates.items()
                ],
            )
            for shop in SHOPS
        )
        await session.flush()
        session.add(issue_to_model(SCENARIO_ISSUE))


async def main() -> None:
    engine = create_async_engine(Settings().database_url)
    await reset_mock_data(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()
    print(f"Reset mock data: {len(TRUCKS)} trucks, {len(SHOPS)} shops, 1 scenario issue.")


if __name__ == "__main__":
    asyncio.run(main())
