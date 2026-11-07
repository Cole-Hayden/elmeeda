import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from issue_tracker.application.booking_service import BookingService
from issue_tracker.application.ports import (
    BookingRejectedError,
    BookingRejection,
    StorageUnavailableError,
)
from issue_tracker.domain.booking import Booking
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.mock_data import (
    MILLRACE_DIESEL,
    ROCKDALE_JUNCTION,
    SCENARIO_ISSUE,
    SHOPS,
    TRUCK_214,
    WOODRIDGE_FLEET,
)
from issue_tracker.infrastructure.models import BookingModel
from issue_tracker.infrastructure.seed import reset_mock_data
from issue_tracker.infrastructure.shop_repository import SqlAlchemyMaintenanceShopRepository
from issue_tracker.infrastructure.truck_repository import SqlAlchemyTruckRepository

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def ready_issue(session_factory: SessionFactory) -> Issue:
    """The scenario issue after the agent has asked whether the truck can be driven."""
    issue = replace(SCENARIO_ISSUE, drivable=False)
    await SqlAlchemyIssueRepository(session_factory).save(issue)
    return issue


async def book(
    session_factory: SessionFactory, issue: Issue, shop: MaintenanceShop
) -> Booking:
    return await BookingService(SqlAlchemyBookingRepository(session_factory)).book(
        issue.issue_id,
        shop.shop_id,
        shop.estimates[ProblemType.COOLANT_LEAK],
        shop.earliest_start,
    )


async def open_bays(session_factory: SessionFactory, shop: MaintenanceShop) -> int:
    shops = await SqlAlchemyMaintenanceShopRepository(session_factory).list_all()
    return next(stored.open_bays for stored in shops if stored.shop_id == shop.shop_id)


async def count_bookings(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(BookingModel))
    assert count is not None
    return count


async def add_ready_copy(session_factory: SessionFactory, issue: Issue) -> Issue:
    copy = replace(issue, issue_id=uuid4())
    await SqlAlchemyIssueRepository(session_factory).add(copy)
    return copy


async def test_truck_is_found_by_the_number_the_dispatcher_says(
    session_factory: SessionFactory,
) -> None:
    repository = SqlAlchemyTruckRepository(session_factory)

    assert await repository.get_by_unit_number("214") == TRUCK_214
    assert await repository.get_by_unit_number("999") is None


async def test_shops_round_trip_with_estimates(session_factory: SessionFactory) -> None:
    stored = await SqlAlchemyMaintenanceShopRepository(session_factory).list_all()

    assert {shop.shop_id: shop for shop in stored} == {shop.shop_id: shop for shop in SHOPS}


async def test_shop_start_time_is_read_back_in_local_time(
    session_factory: SessionFactory,
) -> None:
    stored = await SqlAlchemyMaintenanceShopRepository(session_factory).list_all()
    rockdale = next(shop for shop in stored if shop.shop_id == ROCKDALE_JUNCTION.shop_id)

    assert (rockdale.earliest_start.hour, rockdale.earliest_start.minute) == (15, 30)


async def test_issue_round_trips_every_detail(session_factory: SessionFactory) -> None:
    assert await SqlAlchemyIssueRepository(session_factory).get(
        SCENARIO_ISSUE.issue_id
    ) == SCENARIO_ISSUE


async def test_saving_an_issue_updates_its_details(session_factory: SessionFactory) -> None:
    repository = SqlAlchemyIssueRepository(session_factory)

    await repository.save(replace(SCENARIO_ISSUE, drivable=False))

    stored = await repository.get(SCENARIO_ISSUE.issue_id)
    assert stored is not None
    assert stored.drivable is False
    assert stored.missing_details() == ()


async def test_blank_issue_can_still_be_stored(session_factory: SessionFactory) -> None:
    repository = SqlAlchemyIssueRepository(session_factory)
    issue = Issue.create()

    await repository.add(issue)

    assert await repository.get(issue.issue_id) == issue


async def test_booking_is_stored_and_takes_a_bay(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    booking = await book(session_factory, ready_issue, WOODRIDGE_FLEET)

    stored = await SqlAlchemyBookingRepository(session_factory).get(booking.booking_id)
    assert stored == booking
    assert stored is not None
    assert stored.start_time.hour == 13
    assert await open_bays(session_factory, WOODRIDGE_FLEET) == WOODRIDGE_FLEET.open_bays - 1


async def test_retrying_returns_the_original_booking_without_taking_another_bay(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    first = await book(session_factory, ready_issue, WOODRIDGE_FLEET)
    second = await book(session_factory, ready_issue, WOODRIDGE_FLEET)

    assert second == first
    assert await count_bookings(session_factory) == 1
    assert await open_bays(session_factory, WOODRIDGE_FLEET) == WOODRIDGE_FLEET.open_bays - 1


async def test_booked_issue_cannot_also_be_booked_at_another_shop(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    await book(session_factory, ready_issue, WOODRIDGE_FLEET)

    with pytest.raises(BookingRejectedError) as rejected:
        await book(session_factory, ready_issue, ROCKDALE_JUNCTION)

    assert rejected.value.reason is BookingRejection.ISSUE_ALREADY_BOOKED
    assert await open_bays(session_factory, ROCKDALE_JUNCTION) == ROCKDALE_JUNCTION.open_bays


async def test_shop_with_no_open_bay_rejects_and_saves_nothing(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    other_issue = await add_ready_copy(session_factory, ready_issue)
    await book(session_factory, other_issue, ROCKDALE_JUNCTION)

    with pytest.raises(BookingRejectedError) as rejected:
        await book(session_factory, ready_issue, ROCKDALE_JUNCTION)

    assert rejected.value.reason is BookingRejection.NO_OPEN_BAY
    assert await count_bookings(session_factory) == 1
    assert await open_bays(session_factory, ROCKDALE_JUNCTION) == 0


async def test_two_calls_racing_for_the_last_bay_get_one_booking(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    other_issue = await add_ready_copy(session_factory, ready_issue)

    results = await asyncio.gather(
        book(session_factory, ready_issue, ROCKDALE_JUNCTION),
        book(session_factory, other_issue, ROCKDALE_JUNCTION),
        return_exceptions=True,
    )

    assert sorted(type(result).__name__ for result in results) == [
        "Booking",
        "BookingRejectedError",
    ]
    assert await count_bookings(session_factory) == 1
    assert await open_bays(session_factory, ROCKDALE_JUNCTION) == 0


@pytest.mark.parametrize(
    ("estimate_change", "start_change"),
    [(Decimal("50.00"), timedelta()), (Decimal("0.00"), timedelta(hours=1))],
)
async def test_booking_is_rejected_if_the_confirmed_quote_is_out_of_date(
    session_factory: SessionFactory,
    ready_issue: Issue,
    estimate_change: Decimal,
    start_change: timedelta,
) -> None:
    service = BookingService(SqlAlchemyBookingRepository(session_factory))

    with pytest.raises(BookingRejectedError) as rejected:
        await service.book(
            ready_issue.issue_id,
            WOODRIDGE_FLEET.shop_id,
            WOODRIDGE_FLEET.estimates[ProblemType.COOLANT_LEAK] + estimate_change,
            WOODRIDGE_FLEET.earliest_start + start_change,
        )

    assert rejected.value.reason is BookingRejection.QUOTE_CHANGED
    assert await count_bookings(session_factory) == 0
    assert await open_bays(session_factory, WOODRIDGE_FLEET) == WOODRIDGE_FLEET.open_bays


async def test_shop_that_does_not_repair_the_problem_rejects(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    tire_issue = replace(ready_issue, issue_id=uuid4(), problem=ProblemType.TIRE_BLOWOUT)
    await SqlAlchemyIssueRepository(session_factory).add(tire_issue)

    with pytest.raises(BookingRejectedError) as rejected:
        await book(session_factory, tire_issue, MILLRACE_DIESEL)

    assert rejected.value.reason is BookingRejection.QUOTE_CHANGED


async def test_incomplete_issue_cannot_be_booked(session_factory: SessionFactory) -> None:
    # The seeded issue still doesn't say whether the truck can be driven.
    with pytest.raises(BookingRejectedError) as rejected:
        await book(session_factory, SCENARIO_ISSUE, WOODRIDGE_FLEET)

    assert rejected.value.reason is BookingRejection.ISSUE_INCOMPLETE
    assert await count_bookings(session_factory) == 0


async def test_unknown_issue_and_shop_are_rejected(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    unknown_issue = replace(ready_issue, issue_id=uuid4())
    unknown_shop = replace(WOODRIDGE_FLEET, shop_id=uuid4())

    with pytest.raises(BookingRejectedError) as issue_rejected:
        await book(session_factory, unknown_issue, WOODRIDGE_FLEET)
    with pytest.raises(BookingRejectedError) as shop_rejected:
        await book(session_factory, ready_issue, unknown_shop)

    assert issue_rejected.value.reason is BookingRejection.ISSUE_NOT_FOUND
    assert shop_rejected.value.reason is BookingRejection.SHOP_NOT_FOUND


async def test_reset_restores_the_start_of_the_scenario(
    session_factory: SessionFactory, ready_issue: Issue
) -> None:
    await book(session_factory, ready_issue, ROCKDALE_JUNCTION)
    blank_issue = Issue.create()
    await SqlAlchemyIssueRepository(session_factory).add(blank_issue)

    await reset_mock_data(session_factory)

    assert await count_bookings(session_factory) == 0
    assert await open_bays(session_factory, ROCKDALE_JUNCTION) == ROCKDALE_JUNCTION.open_bays
    issues = SqlAlchemyIssueRepository(session_factory)
    assert await issues.get(SCENARIO_ISSUE.issue_id) == SCENARIO_ISSUE
    assert await issues.get(blank_issue.issue_id) == blank_issue


async def test_unreachable_database_raises_storage_error_when_booking() -> None:
    engine = create_async_engine("postgresql+asyncpg://user:pass@127.0.0.1:1/db")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    with pytest.raises(StorageUnavailableError):
        await book(factory, SCENARIO_ISSUE, WOODRIDGE_FLEET)

    await engine.dispose()
