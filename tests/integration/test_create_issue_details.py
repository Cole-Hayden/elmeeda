from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.booking_service import BookingService
from issue_tracker.domain.issue import FaultCode, ProblemType
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.mock_data import SCENARIO_DAY, SCENARIO_ISSUE, WOODRIDGE_FLEET
from issue_tracker.infrastructure.models import IssueModel

SessionFactory = async_sessionmaker[AsyncSession]

FULL_REQUEST = {
    "truckUnitNumber": "214",
    "problem": "coolant_leak",
    "location": {
        "description": "I-55 near Joliet, IL",
        "latitude": 41.4900,
        "longitude": -88.1950,
    },
    "drivable": False,
    "neededBy": SCENARIO_DAY.isoformat(),
    "maxDistanceMiles": 30,
    "maxBudget": "1500.00",
    "symptoms": "Coolant is leaking under the engine and the temperature is climbing.",
    "contact": {"name": "Fleet Dispatch", "phone": "555-0100"},
    "loaded": True,
    "hazmat": False,
    "odometerMiles": 412000,
    "faultCodes": [{"spn": 110, "fmi": 0}],
}


async def count_issues(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(IssueModel))
    assert count is not None
    return count


async def test_post_issue_persists_every_detail_sent(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    response = await client.post("/issues", json=FULL_REQUEST)

    assert response.status_code == 201
    issue_id = UUID(response.json()["issueId"])
    stored = await SqlAlchemyIssueRepository(session_factory).get(issue_id)
    assert stored == replace(
        SCENARIO_ISSUE,
        issue_id=issue_id,
        drivable=False,
        loaded=True,
        hazmat=False,
        odometer_miles=412000,
        fault_codes=(FaultCode(110, 0),),
    )
    assert stored is not None
    assert stored.missing_details() == ()


async def test_post_issue_accepts_partial_details(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    response = await client.post(
        "/issues", json={"truckUnitNumber": "214", "problem": "coolant_leak"}
    )

    assert response.status_code == 201
    stored = await SqlAlchemyIssueRepository(session_factory).get(
        UUID(response.json()["issueId"])
    )
    assert stored is not None
    assert stored.problem is ProblemType.COOLANT_LEAK
    assert stored.missing_details() == (
        "location",
        "drivable",
        "needed_by",
        "max_distance_miles",
        "max_budget",
        "symptoms",
    )


async def test_post_issue_with_an_unknown_truck_returns_422_and_saves_nothing(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    before = await count_issues(session_factory)

    response = await client.post("/issues", json={"truckUnitNumber": "999"})

    assert response.status_code == 422
    assert response.json() == {"detail": "No truck has that unit number."}
    assert await count_issues(session_factory) == before


async def test_post_issue_with_a_past_needed_by_date_returns_422_and_saves_nothing(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    before = await count_issues(session_factory)
    yesterday = SCENARIO_DAY - timedelta(days=1)

    response = await client.post("/issues", json={"neededBy": yesterday.isoformat()})

    assert response.status_code == 422
    assert response.json() == {"detail": "neededBy can't be in the past."}
    assert await count_issues(session_factory) == before


@pytest.mark.parametrize(
    "invalid",
    [
        {"problem": "flux_capacitor"},
        {"location": {"description": "Nowhere", "latitude": 91, "longitude": 0}},
        {"location": {"description": "Missing coordinates"}},
        {"neededBy": "tomorrow-ish"},
        {"maxDistanceMiles": 0},
        {"maxBudget": "-1.00"},
        {"maxBudget": "1500.001"},
        {"maxBudget": "123456789.00"},
        {"truckUnitNumber": ""},
        {"symptoms": "   "},
        {"contact": {"name": "Only a name"}},
        {"contact": {"name": " ", "phone": "555-0100"}},
        {"odometerMiles": -1},
        {"faultCodes": [{"spn": 524288, "fmi": 0}]},
        {"faultCodes": [{"spn": 110, "fmi": 32}]},
    ],
)
async def test_post_issue_rejects_invalid_details_and_saves_nothing(
    client: AsyncClient, session_factory: SessionFactory, invalid: dict[str, Any]
) -> None:
    before = await count_issues(session_factory)

    response = await client.post("/issues", json=invalid)

    assert response.status_code == 422
    assert await count_issues(session_factory) == before


async def test_issue_created_over_http_can_be_booked(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    response = await client.post("/issues", json=FULL_REQUEST)
    option = next(
        option
        for option in response.json()["options"]
        if option["shopId"] == str(WOODRIDGE_FLEET.shop_id)
    )

    booking = await BookingService(SqlAlchemyBookingRepository(session_factory)).book(
        UUID(response.json()["issueId"]),
        WOODRIDGE_FLEET.shop_id,
        Decimal(option["estimate"]),
        WOODRIDGE_FLEET.earliest_start,
    )

    assert booking.shop_id == WOODRIDGE_FLEET.shop_id
    assert booking.estimate == Decimal("1257.09")
