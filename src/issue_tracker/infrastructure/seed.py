"""Reset the mock data to the start of the scenario.

Run with `uv run python -m issue_tracker.infrastructure.seed`. This deletes all bookings,
trucks, shops, jobs, and any issue attached to a truck.
"""

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from issue_tracker.config import Settings
from issue_tracker.infrastructure.issue_repository import issue_to_model
from issue_tracker.infrastructure.mock_data import JOBS, SCENARIO_ISSUE, SHOPS, TRUCKS
from issue_tracker.infrastructure.models import (
    BookingConfirmationModel,
    BookingModel,
    IssueModel,
    JobModel,
    JobPartModel,
    LimitChangeConfirmationModel,
    MaintenanceShopModel,
    TruckModel,
    VendorCapabilityModel,
)


async def reset_mock_data(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory.begin() as session:
        await session.execute(delete(BookingConfirmationModel))
        await session.execute(delete(LimitChangeConfirmationModel))
        await session.execute(delete(BookingModel))
        await session.execute(delete(IssueModel).where(IssueModel.truck_id.is_not(None)))
        await session.execute(delete(VendorCapabilityModel))
        await session.execute(delete(JobPartModel))
        await session.execute(delete(JobModel))
        await session.execute(delete(MaintenanceShopModel))
        await session.execute(delete(TruckModel))

        session.add_all(
            TruckModel(
                truck_id=truck.truck_id,
                unit_number=truck.unit_number,
                make=truck.make,
                model=truck.model,
                year=truck.year,
                vin=truck.vin,
                engine=truck.engine,
            )
            for truck in TRUCKS
        )
        session.add_all(
            JobModel(
                job_code=job.job_code,
                problem=job.problem.value,
                make=job.make,
                engine=job.engine,
                name=job.name,
                labor_hours=job.labor_hours,
                requires_diagnosis=job.requires_diagnosis,
                vmrs_code=job.vmrs_code,
                parts=[
                    JobPartModel(
                        part_number=part.part_number,
                        description=part.description,
                        quantity=part.quantity,
                        unit_price=part.unit_price,
                    )
                    for part in job.parts
                ],
            )
            for job in JOBS
        )
        await session.flush()
        session.add_all(
            MaintenanceShopModel(
                shop_id=shop.shop_id,
                name=shop.name,
                location_description=shop.location.description,
                latitude=shop.location.latitude,
                longitude=shop.location.longitude,
                open_bays=shop.open_bays,
                earliest_start=shop.earliest_start,
                tow_base_fee=shop.tow.base_fee if shop.tow else None,
                tow_per_mile=shop.tow.per_mile if shop.tow else None,
                tows_hazmat=shop.tow.hazmat if shop.tow else False,
                capabilities=[
                    VendorCapabilityModel(
                        job_code=job_code,
                        labor_rate=capability.labor_rate,
                        authorized_makes=(
                            sorted(capability.authorized_makes)
                            if capability.authorized_makes is not None
                            else None
                        ),
                    )
                    for job_code, capability in shop.capabilities.items()
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
    print(
        f"Reset mock data: {len(TRUCKS)} trucks, {len(JOBS)} jobs, {len(SHOPS)} shops, "
        "1 scenario issue."
    )


if __name__ == "__main__":
    asyncio.run(main())
