from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.booking_service import BookingService
from issue_tracker.domain.issue import ProblemType
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.mock_data import SCENARIO_ISSUE, WOODRIDGE_FLEET
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
    "neededBy": "2026-11-07",
    "maxDistanceMiles": 30,
    "maxBudget": "1500.00",
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
    assert set(response.json()) == {"issueId"}
    issue_id = UUID(response.json()["issueId"])
    stored = await SqlAlchemyIssueRepository(session_factory).get(issue_id)
    assert stored == replace(SCENARIO_ISSUE, issue_id=issue_id, drivable=False)
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
    )


async def test_post_issue_with_an_unknown_truck_returns_422_and_saves_nothing(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    before = await count_issues(session_factory)

    response = await client.post("/issues", json={"truckUnitNumber": "999"})

    assert response.status_code == 422
    assert response.json() == {"detail": "No truck has that unit number."}
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

    booking = await BookingService(SqlAlchemyBookingRepository(session_factory)).book(
        UUID(response.json()["issueId"]),
        WOODRIDGE_FLEET.shop_id,
        WOODRIDGE_FLEET.estimates[ProblemType.COOLANT_LEAK],
        WOODRIDGE_FLEET.earliest_start,
    )

    assert booking.shop_id == WOODRIDGE_FLEET.shop_id
