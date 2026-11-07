import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.booking_service import BookingService
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.mock_data import SCENARIO_DAY, WOODRIDGE_FLEET
from issue_tracker.infrastructure.models import (
    IssueModel,
    JobModel,
    JobPartModel,
    MaintenanceShopModel,
    VendorCapabilityModel,
)

SessionFactory = async_sessionmaker[AsyncSession]

ROCKDALE = "Rockdale Junction Truck Care"
WOODRIDGE = "Woodridge Fleet Service"
MILLRACE = "Millrace Diesel Works"


def request(**overrides: Any) -> dict[str, Any]:
    """A complete request for Truck 214's coolant leak, with a truck that can be driven."""
    return {
        "truckUnitNumber": "214",
        "problem": "coolant_leak",
        "location": {
            "description": "I-55 near Joliet, IL",
            "latitude": 41.4900,
            "longitude": -88.1950,
        },
        "drivable": True,
        "neededBy": SCENARIO_DAY.isoformat(),
        "maxDistanceMiles": 30,
        "maxBudget": "1500.00",
        "symptoms": "Coolant is leaking.",
        "contact": {"name": "Fleet Dispatch", "phone": "555-0100"},
        **overrides,
    }


def reasons(body: dict[str, Any]) -> dict[str, str]:
    return {vendor["name"]: vendor["reason"] for vendor in body["excluded"]}


def estimates(body: dict[str, Any]) -> dict[str, str]:
    return {option["name"]: option["estimate"] for option in body["options"]}


async def create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/issues", json=request(**overrides))
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


async def book_woodridge(session_factory: SessionFactory, body: dict[str, Any]) -> None:
    option = next(option for option in body["options"] if option["name"] == WOODRIDGE)
    await BookingService(SqlAlchemyBookingRepository(session_factory)).book(
        UUID(body["issueId"]),
        WOODRIDGE_FLEET.shop_id,
        Decimal(option["estimate"]),
        WOODRIDGE_FLEET.earliest_start,
    )


async def test_truck_214_drivable_offers_rockdale_and_woodridge_only(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client)

    assert body["status"] == "options_ready"
    assert body["missingDetails"] == []
    assert body["towRequired"] is False
    assert estimates(body) == {WOODRIDGE: "1120.00", ROCKDALE: "1380.00"}
    assert reasons(body) == {MILLRACE: "over_budget"}


async def test_truck_214_with_a_tow_offers_rockdale_and_woodridge_only(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, drivable=False, loaded=True, hazmat=False)

    assert body["status"] == "options_ready"
    assert body["towRequired"] is True
    assert estimates(body) == {WOODRIDGE: "1257.09", ROCKDALE: "1457.19"}
    assert reasons(body) == {MILLRACE: "over_budget"}


async def test_option_has_a_breakdown_and_options_are_in_start_order(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, drivable=False, loaded=True, hazmat=False)

    assert [option["name"] for option in body["options"]] == [WOODRIDGE, ROCKDALE]
    first = body["options"][0]
    assert first["breakdown"] == {"labor": "720.00", "parts": "400.00", "tow": "137.09"}
    assert first["distanceMiles"] == 19.3
    assert first["openBays"] == 2
    assert first["earliestStart"].startswith(SCENARIO_DAY.isoformat())


async def test_response_includes_the_truck_details_and_job(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client)

    assert body["truck"] == {
        "unitNumber": "214",
        "make": "Freightliner",
        "model": "Cascadia",
        "year": 2021,
        "vin": "1TEST000000000214",
        "engine": "DD15",
    }
    assert body["details"]["maxBudget"] == "1500.00"
    assert body["details"]["contact"] == {"name": "Fleet Dispatch", "phone": "555-0100"}
    assert body["details"]["faultCodes"] == []
    assert body["job"]["jobCode"] == "COOLANT_LEAK_GENERIC"
    assert body["job"]["laborHours"] == "4.0"
    assert body["job"]["requiresDiagnosis"] is False
    assert {part["partNumber"] for part in body["job"]["parts"]} == {
        "MOCK-COOL-GAL",
        "MOCK-HOSE-KIT",
    }


async def test_missing_details_use_api_field_names(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    response = await client.post("/issues", json={"problem": "coolant_leak", "drivable": False})
    body = response.json()

    assert body["status"] == "needs_info"
    assert body["missingDetails"] == [
        "truckUnitNumber",
        "location",
        "neededBy",
        "maxDistanceMiles",
        "maxBudget",
        "symptoms",
        "contact",
        "loaded",
        "hazmat",
    ]
    assert body["truck"] is None
    assert body["job"] is None
    assert body["options"] == []
    assert body["excluded"] == []


async def test_brake_failure_requires_a_tow_even_if_reported_drivable(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, problem="brake_failure", drivable=True)

    assert body["towRequired"] is True
    assert body["status"] == "needs_info"
    assert body["missingDetails"] == ["loaded", "hazmat"]


async def test_truck_214_brake_failure_has_no_vendor_within_budget(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, problem="brake_failure", drivable=True, loaded=True, hazmat=False)

    assert body["status"] == "no_vendor"
    assert reasons(body) == {
        ROCKDALE: "job_not_offered",
        WOODRIDGE: "over_budget",
        MILLRACE: "over_budget",
    }


async def test_hazmat_tow_is_limited_to_shops_that_tow_hazmat(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, drivable=False, loaded=True, hazmat=True)

    assert list(estimates(body)) == [WOODRIDGE]
    assert reasons(body) == {
        ROCKDALE: "hazmat_not_supported",
        MILLRACE: "hazmat_not_supported",
    }


async def test_shop_limited_to_other_makes_is_excluded(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, truckUnitNumber="118")

    assert reasons(body)[MILLRACE] == "make_not_supported"


async def test_distance_limit_excludes_farther_shops(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, maxDistanceMiles=10)

    assert list(estimates(body)) == [ROCKDALE]
    assert reasons(body) == {WOODRIDGE: "too_far", MILLRACE: "too_far"}


async def test_unknown_problem_gets_a_diagnostic_job_with_no_parts(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    body = await create(client, problem="unknown")

    assert body["job"]["jobCode"] == "DIAGNOSTIC_GENERIC"
    assert body["job"]["requiresDiagnosis"] is True
    assert body["job"]["parts"] == []
    assert estimates(body) == {WOODRIDGE: "360.00", ROCKDALE: "490.00", MILLRACE: "620.00"}


async def test_make_specific_job_is_chosen_over_the_generic_one(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    async with session_factory.begin() as session:
        session.add(
            JobModel(
                job_code="COOLANT_LEAK_FREIGHTLINER",
                problem="coolant_leak",
                make="Freightliner",
                name="Coolant leak repair, Freightliner",
                labor_hours=Decimal("3.0"),
                requires_diagnosis=False,
                parts=[
                    JobPartModel(
                        part_number="MOCK-F-KIT",
                        description="Hose kit",
                        quantity=1,
                        unit_price=Decimal("100.00"),
                    )
                ],
            )
        )
        await session.flush()
        session.add(
            VendorCapabilityModel(
                shop_id=WOODRIDGE_FLEET.shop_id,
                job_code="COOLANT_LEAK_FREIGHTLINER",
                labor_rate=Decimal("100.00"),
            )
        )

    freightliner = await create(client)
    kenworth = await create(client, truckUnitNumber="118")

    assert freightliner["job"]["jobCode"] == "COOLANT_LEAK_FREIGHTLINER"
    assert estimates(freightliner) == {WOODRIDGE: "400.00"}
    assert reasons(freightliner)[ROCKDALE] == "job_not_offered"
    assert kenworth["job"]["jobCode"] == "COOLANT_LEAK_GENERIC"


async def test_same_key_returns_the_same_issue(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    key = str(uuid4())

    first = await client.post("/issues", headers={"Idempotency-Key": key})
    second = await client.post("/issues", headers={"Idempotency-Key": key})

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["issueId"] == second.json()["issueId"]


async def test_retry_with_a_different_body_returns_the_original_details(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    key = str(uuid4())

    await client.post("/issues", headers={"Idempotency-Key": key}, json={"symptoms": "Original"})
    retried = await client.post(
        "/issues", headers={"Idempotency-Key": key}, json={"symptoms": "New"}
    )

    assert retried.status_code == 200
    assert retried.json()["details"]["symptoms"] == "Original"


async def test_concurrent_requests_with_one_key_create_one_issue(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    key = str(uuid4())

    responses = await asyncio.gather(
        *(client.post("/issues", headers={"Idempotency-Key": key}) for _ in range(5))
    )

    assert sorted(response.status_code for response in responses) == [200, 200, 200, 200, 201]
    assert len({response.json()["issueId"] for response in responses}) == 1
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(IssueModel)
            .where(IssueModel.idempotency_key == key)
        )
    assert count == 1


async def test_get_returns_the_stored_issue_and_triage(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client, drivable=False, loaded=True, hazmat=False)

    response = await client.get(f"/issues/{created['issueId']}")

    assert response.status_code == 200
    assert response.json() == created


async def test_get_unknown_issue_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/issues/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "No issue has that ID."}


async def test_status_reflects_availability_on_every_read(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)
    assert created["status"] == "options_ready"

    async with session_factory.begin() as session:
        await session.execute(update(MaintenanceShopModel).values(open_bays=0))
    response = await client.get(f"/issues/{created['issueId']}")

    assert response.json()["status"] == "no_vendor"
    assert reasons(response.json()) == {
        ROCKDALE: "no_open_bay",
        WOODRIDGE: "no_open_bay",
        MILLRACE: "over_budget",
    }


async def test_price_reflects_a_changed_labor_rate_on_the_next_read(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)

    async with session_factory.begin() as session:
        await session.execute(
            update(VendorCapabilityModel)
            .where(VendorCapabilityModel.shop_id == WOODRIDGE_FLEET.shop_id)
            .where(VendorCapabilityModel.job_code == "COOLANT_LEAK_GENERIC")
            .values(labor_rate=Decimal("200.00"))
        )
    response = await client.get(f"/issues/{created['issueId']}")

    assert estimates(response.json())[WOODRIDGE] == "1200.00"


async def test_booked_issue_reports_booked_with_no_options(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)
    await book_woodridge(session_factory, created)

    response = await client.get(f"/issues/{created['issueId']}")

    assert response.json()["status"] == "booked"
    assert response.json()["options"] == []
    assert response.json()["excluded"] == []


async def test_patch_fills_in_details_until_options_are_ready(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    response = await client.post(
        "/issues", json={"truckUnitNumber": "214", "problem": "coolant_leak"}
    )
    url = f"/issues/{response.json()['issueId']}"

    remaining = {key: value for key, value in request().items() if key != "truckUnitNumber"}
    for field, value in remaining.items():
        response = await client.patch(url, json={field: value})
        assert response.status_code == 200

    assert response.json()["status"] == "options_ready"
    assert response.json()["missingDetails"] == []
    assert estimates(response.json()) == {WOODRIDGE: "1120.00", ROCKDALE: "1380.00"}


async def test_patch_changes_only_what_was_sent(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)

    response = await client.patch(
        f"/issues/{created['issueId']}", json={"symptoms": "Now also steaming."}
    )

    assert response.json()["details"] == {**created["details"], "symptoms": "Now also steaming."}


@pytest.mark.parametrize("field", ["symptoms", "drivable", "contact"])
async def test_patch_with_null_leaves_the_detail_unchanged(
    client: AsyncClient, session_factory: SessionFactory, field: str
) -> None:
    created = await create(client)

    response = await client.patch(f"/issues/{created['issueId']}", json={field: None})

    assert response.status_code == 200
    assert response.json()["details"] == created["details"]


async def test_patch_that_requires_a_tow_asks_for_tow_details_and_reprices(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)
    url = f"/issues/{created['issueId']}"

    asked = await client.patch(url, json={"drivable": False})
    answered = await client.patch(url, json={"loaded": False, "hazmat": False})

    assert asked.json()["status"] == "needs_info"
    assert asked.json()["missingDetails"] == ["loaded", "hazmat"]
    assert estimates(answered.json())[WOODRIDGE] == "1257.09"


@pytest.mark.parametrize(
    "invalid",
    [
        {"truckUnitNumber": "999"},
        {"problem": "flux_capacitor"},
        {"maxBudget": "-1.00"},
        {"neededBy": "2000-01-01"},
    ],
)
async def test_invalid_patch_returns_422_and_changes_nothing(
    client: AsyncClient, session_factory: SessionFactory, invalid: dict[str, Any]
) -> None:
    created = await create(client)
    url = f"/issues/{created['issueId']}"

    response = await client.patch(url, json=invalid)

    assert response.status_code == 422
    assert (await client.get(url)).json() == created


async def test_patch_unknown_issue_returns_404(client: AsyncClient) -> None:
    response = await client.patch(f"/issues/{uuid4()}", json={"drivable": True})

    assert response.status_code == 404


async def test_patch_booked_issue_returns_409_and_changes_nothing(
    client: AsyncClient, session_factory: SessionFactory
) -> None:
    created = await create(client)
    await book_woodridge(session_factory, created)
    url = f"/issues/{created['issueId']}"

    response = await client.patch(url, json={"drivable": False})

    assert response.status_code == 409
    assert (await client.get(url)).json()["details"] == created["details"]
