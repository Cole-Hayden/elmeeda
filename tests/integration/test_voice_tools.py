from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.infrastructure.mock_data import SCENARIO_DAY
from issue_tracker.infrastructure.models import (
    BookingModel,
    IssueModel,
    MaintenanceShopModel,
    VendorCapabilityModel,
)

SessionFactory = async_sessionmaker[AsyncSession]

ROCKDALE = "Rockdale Junction Truck Care"
WOODRIDGE = "Woodridge Fleet Service"
MILLRACE = "Millrace Diesel Works"


OPENING_REQUEST = {
    "truckUnitNumber": "214",
    "place": "I-55 near Joliet",
    "problem": "coolant_leak",
    "symptoms": "Coolant leak",
    "neededBy": SCENARIO_DAY.isoformat(),
    "maxDistanceMiles": 30,
    "maxBudget": 1500,
}


async def tool(client: AsyncClient, issue_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    response = await client.post(f"/voice/calls/{issue_id}/tools/{name}", json=arguments)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


@pytest.fixture
async def issue_id(client: AsyncClient, session_factory: SessionFactory) -> str:
    response = await client.post("/issues")
    issue: str = response.json()["issueId"]
    return issue


@pytest.fixture
async def ready_issue_id(client: AsyncClient, issue_id: str) -> str:
    """Truck 214 with everything said and a truck that can be driven."""
    await tool(client, issue_id, "update_issue", **OPENING_REQUEST, drivable=True)
    return issue_id


async def shop_id(client: AsyncClient, issue_id: str, name: str) -> str:
    result = await tool(client, issue_id, "search_shops")
    found: str = next(
        vendor["shopId"]
        for vendor in result["options"] + result["excluded"] + result["unavailable"]
        if vendor["name"] == name
    )
    return found


async def prepare_only(client: AsyncClient, issue_id: str, name: str) -> dict[str, Any]:
    return await tool(
        client, issue_id, "prepare_booking", shopId=await shop_id(client, issue_id, name)
    )


async def read_back(client: AsyncClient, issue_id: str, prepared: dict[str, Any], text: str) -> Any:
    response = await client.post(
        f"/voice/calls/{issue_id}/read-backs",
        json={"confirmationId": prepared["confirmationId"], "text": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def prepare(client: AsyncClient, issue_id: str, name: str) -> dict[str, Any]:
    """Prepare a booking and have the agent read it back in full."""
    prepared = await prepare_only(client, issue_id, name)
    assert (await read_back(client, issue_id, prepared, prepared["readBack"]))["matched"] is True
    return prepared


async def answer(client: AsyncClient, issue_id: str, prepared: dict[str, Any], text: str) -> Any:
    response = await client.post(
        f"/voice/calls/{issue_id}/answers",
        json={"confirmationId": prepared["confirmationId"], "text": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def confirmed_booking(client: AsyncClient, issue_id: str, name: str) -> dict[str, Any]:
    prepared = await prepare(client, issue_id, name)
    await answer(client, issue_id, prepared, "Yes, book it.")
    return await tool(client, issue_id, "book_repair", shopId=prepared["shopId"])


async def set_fault(client: AsyncClient, issue_id: str, name: str, fault: str) -> None:
    response = await client.put(
        f"/voice/shops/{await shop_id(client, issue_id, name)}/fault", json={"fault": fault}
    )
    assert response.status_code == 200, response.text


async def count_bookings(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        return len((await session.scalars(select(BookingModel))).all())


async def test_opening_request_leaves_only_drivable_missing(
    client: AsyncClient, issue_id: str
) -> None:
    result = await tool(client, issue_id, "update_issue", **OPENING_REQUEST)

    assert result["missingDetails"] == ["drivable"]
    assert result["status"] == "needs_info"
    assert result["details"]["location"]["description"] == "I-55 near Joliet, IL"
    assert "issueId" not in result
    assert "options" not in result


async def test_truck_that_cannot_drive_also_asks_about_its_load(
    client: AsyncClient, issue_id: str
) -> None:
    result = await tool(client, issue_id, "update_issue", **OPENING_REQUEST, drivable=False)

    assert result["towRequired"] is True
    assert result["missingDetails"] == ["loaded", "hazmat"]


async def test_unknown_place_is_reported_and_other_details_are_kept(
    client: AsyncClient, issue_id: str
) -> None:
    result = await tool(
        client, issue_id, "update_issue", place="somewhere in Nebraska", problem="coolant_leak"
    )

    assert result["error"] == "location_unknown"
    assert result["details"]["location"] is None
    assert result["details"]["problem"] == "coolant_leak"
    assert "location" in result["missingDetails"]


async def test_coordinates_from_the_model_are_ignored(client: AsyncClient, issue_id: str) -> None:
    result = await tool(
        client,
        issue_id,
        "update_issue",
        location={"description": "Made up", "latitude": 1.0, "longitude": 2.0},
    )

    assert result["details"]["location"] is None


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"truckUnitNumber": "999"}, "unknown_truck"),
        ({"neededBy": "2000-01-01"}, "needed_by_in_past"),
        ({"problem": "flat_battery"}, "invalid_arguments"),
        ({"maxBudget": -5}, "invalid_arguments"),
    ],
)
async def test_bad_details_are_explained_and_not_saved(
    client: AsyncClient, issue_id: str, arguments: dict[str, Any], error: str
) -> None:
    result = await tool(client, issue_id, "update_issue", **arguments)

    assert result["error"] == error
    state = await client.get(f"/issues/{issue_id}")
    assert state.json()["details"]["problem"] is None


async def test_search_offers_only_eligible_shops_with_reasons(
    client: AsyncClient, ready_issue_id: str
) -> None:
    result = await tool(client, ready_issue_id, "search_shops")

    assert result["status"] == "options_ready"
    assert {option["name"]: option["estimate"] for option in result["options"]} == {
        ROCKDALE: "1380.00",
        WOODRIDGE: "1120.00",
    }
    assert [(shop["name"], shop["reason"]) for shop in result["excluded"]] == [
        (MILLRACE, "over_budget")
    ]


async def test_prepare_returns_the_current_quote_and_books_nothing(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    result = await tool(
        client,
        ready_issue_id,
        "prepare_booking",
        shopId=await shop_id(client, ready_issue_id, WOODRIDGE),
    )

    assert result["shopName"] == WOODRIDGE
    assert result["estimate"] == "1120.00"
    assert result["startTime"].endswith("-06:00")
    async with session_factory() as session:
        assert await session.scalar(select(BookingModel)) is None


async def test_prepare_refuses_an_excluded_shop_with_its_reason(
    client: AsyncClient, ready_issue_id: str
) -> None:
    result = await tool(
        client,
        ready_issue_id,
        "prepare_booking",
        shopId=await shop_id(client, ready_issue_id, MILLRACE),
    )

    assert result == {"error": "shop_not_available", "reason": "over_budget"}


async def test_prepare_refuses_a_made_up_shop(client: AsyncClient, ready_issue_id: str) -> None:
    result = await tool(client, ready_issue_id, "prepare_booking", shopId=str(uuid4()))

    assert result == {"error": "shop_not_available", "reason": None}


async def test_book_creates_the_booking_and_takes_a_bay(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    assert (await answer(client, ready_issue_id, prepared, "Yes, book it."))["confirmed"] is True

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result["bookingId"].startswith("BK-")
    assert result["shopName"] == WOODRIDGE
    assert result["estimate"] == prepared["estimate"]
    assert result["startTime"] == prepared["startTime"]
    assert "alreadyBooked" not in result
    async with session_factory() as session:
        booking = await session.get(BookingModel, result["bookingId"])
        shop = await session.scalar(
            select(MaintenanceShopModel).where(MaintenanceShopModel.name == WOODRIDGE)
        )
    assert booking is not None
    assert shop is not None and shop.open_bays == 1


async def test_booking_without_preparing_is_refused(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    woodridge = await shop_id(client, ready_issue_id, WOODRIDGE)

    result = await tool(client, ready_issue_id, "book_repair", shopId=woodridge)

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_booking_before_the_dispatcher_answers_is_refused(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


@pytest.mark.parametrize(
    "reply", ["No, hold on.", "Wait a second.", "Um, let me think.", "What was the price?"]
)
async def test_booking_after_anything_but_a_yes_is_refused(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str, reply: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    assert (await answer(client, ready_issue_id, prepared, reply))["confirmed"] is False

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_booking_before_the_details_were_said_is_refused(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare_only(client, ready_issue_id, WOODRIDGE)

    reply = await answer(client, ready_issue_id, prepared, "Okay.")
    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert reply["confirmed"] is False
    assert result == {"error": "read_back_required"}
    assert await count_bookings(session_factory) == 0


async def test_yes_before_the_read_back_does_not_carry_over(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare_only(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    await read_back(client, ready_issue_id, prepared, prepared["readBack"])

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


@pytest.mark.parametrize(
    "spoken",
    [
        "Should I go ahead and book it?",
        "Woodridge Fleet Service, starting at the time shown on screen. Should I book it?",
        "Woodridge Fleet Service for $900. Should I book it?",
    ],
)
async def test_read_back_missing_or_misstating_details_blocks_the_yes(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str, spoken: str
) -> None:
    prepared = await prepare_only(client, ready_issue_id, WOODRIDGE)

    assert (await read_back(client, ready_issue_id, prepared, spoken))["matched"] is False
    reply = await answer(client, ready_issue_id, prepared, "Yes.")
    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert reply["confirmed"] is False
    assert result == {"error": "read_back_required"}
    assert await count_bookings(session_factory) == 0


async def test_a_correct_read_back_after_a_failed_one_allows_the_yes(
    client: AsyncClient, ready_issue_id: str
) -> None:
    prepared = await prepare_only(client, ready_issue_id, WOODRIDGE)
    await read_back(client, ready_issue_id, prepared, "Should I book it?")
    await read_back(client, ready_issue_id, prepared, prepared["readBack"])
    await answer(client, ready_issue_id, prepared, "Yes.")

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result["bookingId"].startswith("BK-")


async def test_speech_after_the_yes_does_not_cancel_the_booking(
    client: AsyncClient, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    await read_back(client, ready_issue_id, prepared, "Booking that now.")

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result["bookingId"].startswith("BK-")


async def test_read_back_of_an_earlier_shop_does_not_count(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    first = await prepare_only(client, ready_issue_id, WOODRIDGE)
    second = await prepare_only(client, ready_issue_id, ROCKDALE)

    late = await read_back(client, ready_issue_id, first, first["readBack"])
    await answer(client, ready_issue_id, second, "Yes.")
    result = await tool(client, ready_issue_id, "book_repair", shopId=second["shopId"])

    assert late["matched"] is False
    assert result == {"error": "read_back_required"}
    assert await count_bookings(session_factory) == 0


async def test_preparing_again_needs_a_new_read_back(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    await prepare(client, ready_issue_id, WOODRIDGE)
    again = await prepare_only(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, again, "Yes.")

    result = await tool(client, ready_issue_id, "book_repair", shopId=again["shopId"])

    assert result == {"error": "read_back_required"}
    assert await count_bookings(session_factory) == 0


async def test_the_latest_answer_decides(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    await answer(client, ready_issue_id, prepared, "Actually, wait.")

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_yes_to_one_shop_does_not_book_another(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    rockdale = await shop_id(client, ready_issue_id, ROCKDALE)

    result = await tool(client, ready_issue_id, "book_repair", shopId=rockdale)

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_preparing_another_shop_cancels_the_earlier_yes(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    first = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, first, "Yes.")
    second = await prepare(client, ready_issue_id, ROCKDALE)

    # A late transcript of the yes to Woodridge must not confirm Rockdale.
    late = await answer(client, ready_issue_id, first, "Yes.")
    result = await tool(client, ready_issue_id, "book_repair", shopId=second["shopId"])

    assert late["confirmed"] is False
    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_model_arguments_cannot_change_the_booked_price(
    client: AsyncClient, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")

    result = await tool(
        client,
        ready_issue_id,
        "book_repair",
        shopId=prepared["shopId"],
        estimate="1.00",
        startTime="2000-01-01T00:00:00+00:00",
    )

    assert result["estimate"] == prepared["estimate"]
    assert result["startTime"] == prepared["startTime"]


async def test_no_booked_repairs_are_listed_before_a_booking(
    client: AsyncClient, ready_issue_id: str
) -> None:
    await prepare(client, ready_issue_id, WOODRIDGE)

    response = await client.get("/voice/bookings")

    assert response.status_code == 200
    assert response.json() == []


async def test_booked_repair_is_listed_with_its_details(
    client: AsyncClient, ready_issue_id: str
) -> None:
    booked = await confirmed_booking(client, ready_issue_id, WOODRIDGE)
    await client.post("/issues")

    response = await client.get("/voice/bookings")

    assert response.status_code == 200
    assert response.json() == [
        {
            "bookingId": booked["bookingId"],
            "truckUnitNumber": "214",
            "problem": "coolant_leak",
            "location": "I-55 near Joliet, IL",
            "shopName": WOODRIDGE,
            "estimate": "1120.00",
            "startTime": booked["startTime"],
        }
    ]


async def test_second_yes_returns_the_same_booking(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    first = await confirmed_booking(client, ready_issue_id, WOODRIDGE)

    second = await tool(client, ready_issue_id, "book_repair", shopId=first["shopId"])

    assert second["bookingId"] == first["bookingId"]
    assert second["alreadyBooked"] is True
    assert await count_bookings(session_factory) == 1
    async with session_factory() as session:
        shop = await session.scalar(
            select(MaintenanceShopModel).where(MaintenanceShopModel.name == WOODRIDGE)
        )
    assert shop is not None and shop.open_bays == 1


async def test_a_new_call_for_the_same_truck_finds_the_booking(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    first = await confirmed_booking(client, ready_issue_id, WOODRIDGE)
    new_call = (await client.post("/issues")).json()["issueId"]
    await tool(client, new_call, "update_issue", **OPENING_REQUEST, drivable=True)

    search = await tool(client, new_call, "search_shops")
    prepared = await tool(client, new_call, "prepare_booking", shopId=first["shopId"])
    booked = await tool(client, new_call, "book_repair", shopId=first["shopId"])

    assert search["status"] == "booked"
    assert search["options"] == []
    assert search["existingBooking"]["bookingId"] == first["bookingId"]
    assert prepared == {"error": "shop_not_available", "reason": "already_booked"}
    assert booked["bookingId"] == first["bookingId"]
    assert booked["alreadyBooked"] is True
    assert await count_bookings(session_factory) == 1


async def test_a_new_call_for_another_day_finds_the_booking(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    first = await confirmed_booking(client, ready_issue_id, WOODRIDGE)
    new_call = (await client.post("/issues")).json()["issueId"]
    tomorrow = (SCENARIO_DAY + timedelta(days=1)).isoformat()
    await tool(
        client,
        new_call,
        "update_issue",
        **{**OPENING_REQUEST, "neededBy": tomorrow, "maxBudget": 9000},
        drivable=True,
    )

    search = await tool(client, new_call, "search_shops")
    prepared = await tool(client, new_call, "prepare_booking", shopId=first["shopId"])
    booked = await tool(client, new_call, "book_repair", shopId=first["shopId"])

    assert search["status"] == "booked"
    assert search["options"] == []
    assert search["existingBooking"]["bookingId"] == first["bookingId"]
    assert prepared == {"error": "shop_not_available", "reason": "already_booked"}
    assert booked["bookingId"] == first["bookingId"]
    assert booked["alreadyBooked"] is True
    assert await count_bookings(session_factory) == 1


async def test_shop_that_loses_its_last_bay_rejects_truthfully(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, ROCKDALE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    async with session_factory.begin() as session:
        await session.execute(
            update(MaintenanceShopModel)
            .where(MaintenanceShopModel.name == ROCKDALE)
            .values(open_bays=0)
        )

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "no_open_bay"}
    assert await count_bookings(session_factory) == 0

    # Searching again leaves the other shop for the agent to offer.
    again = await tool(client, ready_issue_id, "search_shops")
    assert [option["name"] for option in again["options"]] == [WOODRIDGE]


async def test_changed_price_rejects_the_booking(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    async with session_factory.begin() as session:
        await session.execute(
            update(VendorCapabilityModel)
            .where(VendorCapabilityModel.shop_id == prepared["shopId"])
            .values(labor_rate=Decimal("200.00"))
        )

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "quote_changed"}
    assert await count_bookings(session_factory) == 0


async def test_rejected_booking_needs_a_new_yes(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    prepared = await prepare(client, ready_issue_id, WOODRIDGE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    await set_fault(client, ready_issue_id, WOODRIDGE, "error")
    await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])
    await set_fault(client, ready_issue_id, WOODRIDGE, "none")

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": "confirmation_required"}
    assert await count_bookings(session_factory) == 0


async def test_details_cannot_change_after_booking(
    client: AsyncClient, session_factory: SessionFactory, ready_issue_id: str
) -> None:
    await confirmed_booking(client, ready_issue_id, WOODRIDGE)

    result = await tool(client, ready_issue_id, "update_issue", drivable=False)

    assert result == {"error": "issue_already_booked"}
    async with session_factory() as session:
        issue = await session.get(IssueModel, ready_issue_id)
    assert issue is not None and issue.drivable is True


@pytest.mark.parametrize(
    ("fault", "reason"), [("timeout", "shop_timeout"), ("error", "shop_error")]
)
async def test_failing_shop_is_reported_and_the_others_still_answer(
    client: AsyncClient, ready_issue_id: str, fault: str, reason: str
) -> None:
    await set_fault(client, ready_issue_id, ROCKDALE, fault)

    result = await tool(client, ready_issue_id, "search_shops")

    assert result["status"] == "options_ready"
    assert [option["name"] for option in result["options"]] == [WOODRIDGE]
    assert [(shop["name"], shop["reason"]) for shop in result["unavailable"]] == [
        (ROCKDALE, reason)
    ]
    # The dispatcher's limits are still on the issue.
    assert result["details"]["maxBudget"] == "1500.00"
    assert result["details"]["maxDistanceMiles"] == 30


async def test_no_open_bay_switch_excludes_the_shop(
    client: AsyncClient, ready_issue_id: str
) -> None:
    await set_fault(client, ready_issue_id, ROCKDALE, "no_open_bay")

    result = await tool(client, ready_issue_id, "search_shops")

    assert [option["name"] for option in result["options"]] == [WOODRIDGE]
    assert (ROCKDALE, "no_open_bay") in [
        (shop["name"], shop["reason"]) for shop in result["excluded"]
    ]
    assert result["unavailable"] == []


async def test_every_shop_failing_leaves_no_options(
    client: AsyncClient, ready_issue_id: str
) -> None:
    for name in (ROCKDALE, WOODRIDGE, MILLRACE):
        await set_fault(client, ready_issue_id, name, "error")

    result = await tool(client, ready_issue_id, "search_shops")

    assert result["status"] == "shops_unavailable"
    assert result["options"] == []
    assert len(result["unavailable"]) == 3


@pytest.mark.parametrize(
    ("fault", "error"),
    [("timeout", "shop_timeout"), ("error", "shop_error"), ("no_open_bay", "no_open_bay")],
)
async def test_switch_flipped_after_the_yes_blocks_the_booking(
    client: AsyncClient,
    session_factory: SessionFactory,
    ready_issue_id: str,
    fault: str,
    error: str,
) -> None:
    prepared = await prepare(client, ready_issue_id, ROCKDALE)
    await answer(client, ready_issue_id, prepared, "Yes.")
    await set_fault(client, ready_issue_id, ROCKDALE, fault)

    result = await tool(client, ready_issue_id, "book_repair", shopId=prepared["shopId"])

    assert result == {"error": error}
    assert await count_bookings(session_factory) == 0
    async with session_factory() as session:
        shop = await session.scalar(
            select(MaintenanceShopModel).where(MaintenanceShopModel.name == ROCKDALE)
        )
    assert shop is not None and shop.open_bays == 1


async def test_preparing_a_failing_shop_is_refused_with_the_reason(
    client: AsyncClient, ready_issue_id: str
) -> None:
    rockdale = await shop_id(client, ready_issue_id, ROCKDALE)
    await set_fault(client, ready_issue_id, ROCKDALE, "error")

    result = await tool(client, ready_issue_id, "prepare_booking", shopId=rockdale)

    assert result == {"error": "shop_not_available", "reason": "shop_error"}


async def test_failure_switch_lists_shops_and_clears(
    client: AsyncClient, ready_issue_id: str
) -> None:
    await set_fault(client, ready_issue_id, ROCKDALE, "timeout")
    shops = (await client.get("/voice/shops")).json()
    assert {shop["name"]: shop["fault"] for shop in shops} == {
        ROCKDALE: "timeout",
        WOODRIDGE: "none",
        MILLRACE: "none",
    }

    await set_fault(client, ready_issue_id, ROCKDALE, "none")

    result = await tool(client, ready_issue_id, "search_shops")
    assert {option["name"] for option in result["options"]} == {ROCKDALE, WOODRIDGE}


async def test_failure_switch_refuses_an_unknown_shop(client: AsyncClient) -> None:
    response = await client.put(f"/voice/shops/{uuid4()}/fault", json={"fault": "error"})

    assert response.status_code == 404


async def test_rest_reads_are_not_affected_by_the_switch(
    client: AsyncClient, ready_issue_id: str
) -> None:
    await set_fault(client, ready_issue_id, ROCKDALE, "timeout")

    result = (await client.get(f"/issues/{ready_issue_id}")).json()

    assert {option["name"] for option in result["options"]} == {ROCKDALE, WOODRIDGE}


async def test_unknown_issue_returns_404(client: AsyncClient) -> None:
    response = await client.post(f"/voice/calls/{uuid4()}/tools/search_shops", json={})

    assert response.status_code == 404


async def test_unknown_tool_is_refused(client: AsyncClient, issue_id: str) -> None:
    response = await client.post(f"/voice/calls/{issue_id}/tools/delete_everything", json={})

    assert response.status_code == 422
