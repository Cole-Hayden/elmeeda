"""Recovering from a shop failure without the model loosening what the dispatcher asked for."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.infrastructure.mock_data import SCENARIO_DAY

ROCKDALE = "Rockdale Junction Truck Care"
WOODRIDGE = "Woodridge Fleet Service"
MILLRACE = "Millrace Diesel Works"
ALL_SHOPS = (ROCKDALE, WOODRIDGE, MILLRACE)


async def tool(client: AsyncClient, issue_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    response = await client.post(f"/voice/calls/{issue_id}/tools/{name}", json=arguments)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def answer(client: AsyncClient, issue_id: str, confirmation_id: str, text: str) -> Any:
    response = await client.post(
        f"/voice/calls/{issue_id}/answers",
        json={"confirmationId": confirmation_id, "text": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def set_fault(client: AsyncClient, name: str, fault: str) -> None:
    shops = (await client.get("/voice/shops")).json()
    shop_id = next(shop["shopId"] for shop in shops if shop["name"] == name)
    response = await client.put(f"/voice/shops/{shop_id}/fault", json={"fault": fault})
    assert response.status_code == 200, response.text


@pytest.fixture
async def issue_id(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> str:
    """Truck 214 with a $1,500 budget, a 30 mile limit, and every other detail said."""
    created: str = (await client.post("/issues")).json()["issueId"]
    await tool(
        client,
        created,
        "update_issue",
        truckUnitNumber="214",
        place="I-55 near Joliet",
        problem="coolant_leak",
        symptoms="Coolant leak",
        neededBy=SCENARIO_DAY.isoformat(),
        maxDistanceMiles=30,
        maxBudget=1500,
        drivable=True,
    )
    return created


LATER = (SCENARIO_DAY + timedelta(days=1)).isoformat()


@pytest.mark.parametrize(
    ("arguments", "field", "saved"),
    [
        ({"maxBudget": 5000}, "maxBudget", "1500.00"),
        ({"maxDistanceMiles": 500}, "maxDistanceMiles", 30),
        ({"neededBy": LATER}, "neededBy", SCENARIO_DAY.isoformat()),
    ],
)
async def test_loosening_a_limit_is_not_saved_without_a_yes(
    client: AsyncClient, issue_id: str, arguments: dict[str, Any], field: str, saved: Any
) -> None:
    result = await tool(client, issue_id, "update_issue", **arguments)

    assert field in result["limitChangeNeedsYes"]
    assert result["details"][field] == saved
    assert (await client.get(f"/issues/{issue_id}")).json()["details"][field] == saved


async def test_search_keeps_the_old_limit_until_the_dispatcher_agrees(
    client: AsyncClient, issue_id: str
) -> None:
    await tool(client, issue_id, "update_issue", maxBudget=5000)

    result = await tool(client, issue_id, "search_shops")

    assert (MILLRACE, "over_budget") in [(s["name"], s["reason"]) for s in result["excluded"]]


async def test_yes_to_the_read_back_lets_the_same_change_through(
    client: AsyncClient, issue_id: str
) -> None:
    asked = await tool(client, issue_id, "update_issue", maxBudget=5000)
    reply = await answer(client, issue_id, asked["confirmationId"], "Yes.")

    result = await tool(client, issue_id, "update_issue", maxBudget=5000)

    assert reply["confirmed"] is True
    assert "limitChangeNeedsYes" not in result
    assert Decimal(result["details"]["maxBudget"]) == 5000


@pytest.mark.parametrize("reply", ["No, keep it.", "Um, let me think.", "What would that cost?"])
async def test_anything_but_a_yes_leaves_the_limit(
    client: AsyncClient, issue_id: str, reply: str
) -> None:
    asked = await tool(client, issue_id, "update_issue", maxBudget=5000)
    await answer(client, issue_id, asked["confirmationId"], reply)

    result = await tool(client, issue_id, "update_issue", maxBudget=5000)

    assert Decimal(result["details"]["maxBudget"]) == 1500
    assert result["confirmationId"] == asked["confirmationId"]


async def test_yes_to_one_value_does_not_allow_a_higher_one(
    client: AsyncClient, issue_id: str
) -> None:
    asked = await tool(client, issue_id, "update_issue", maxBudget=2000)
    await answer(client, issue_id, asked["confirmationId"], "Yes.")

    result = await tool(client, issue_id, "update_issue", maxBudget=9000)

    assert result["limitChangeNeedsYes"] == {"maxBudget": "9000"}
    assert Decimal(result["details"]["maxBudget"]) == 1500
    assert (await answer(client, issue_id, asked["confirmationId"], "Yes."))["confirmed"] is False


async def test_a_yes_only_counts_once(client: AsyncClient, issue_id: str) -> None:
    asked = await tool(client, issue_id, "update_issue", maxBudget=2000)
    await answer(client, issue_id, asked["confirmationId"], "Yes.")
    await tool(client, issue_id, "update_issue", maxBudget=2000)

    result = await tool(client, issue_id, "update_issue", maxBudget=3000)

    assert result["limitChangeNeedsYes"] == {"maxBudget": "3000"}
    assert Decimal(result["details"]["maxBudget"]) == 2000


async def test_yes_to_a_booking_does_not_loosen_a_limit(client: AsyncClient, issue_id: str) -> None:
    search = await tool(client, issue_id, "search_shops")
    prepared = await tool(
        client, issue_id, "prepare_booking", shopId=search["options"][0]["shopId"]
    )
    await tool(client, issue_id, "update_issue", maxBudget=5000)
    await answer(client, issue_id, prepared["confirmationId"], "Yes.")

    result = await tool(client, issue_id, "update_issue", maxBudget=5000)

    assert Decimal(result["details"]["maxBudget"]) == 1500


async def test_other_details_are_saved_while_a_limit_waits(
    client: AsyncClient, issue_id: str
) -> None:
    result = await tool(client, issue_id, "update_issue", maxBudget=5000, symptoms="Losing coolant")

    assert result["details"]["symptoms"] == "Losing coolant"
    assert Decimal(result["details"]["maxBudget"]) == 1500


async def test_tightening_a_limit_needs_no_yes(client: AsyncClient, issue_id: str) -> None:
    result = await tool(client, issue_id, "update_issue", maxBudget=1000, maxDistanceMiles=10)

    assert "limitChangeNeedsYes" not in result
    assert Decimal(result["details"]["maxBudget"]) == 1000
    assert result["details"]["maxDistanceMiles"] == 10


async def test_setting_a_limit_for_the_first_time_needs_no_yes(client: AsyncClient) -> None:
    created = (await client.post("/issues")).json()["issueId"]

    result = await tool(client, created, "update_issue", maxBudget=9000)

    assert "limitChangeNeedsYes" not in result
    assert Decimal(result["details"]["maxBudget"]) == 9000


async def test_booked_issue_does_not_ask_about_a_limit(client: AsyncClient, issue_id: str) -> None:
    search = await tool(client, issue_id, "search_shops")
    prepared = await tool(
        client, issue_id, "prepare_booking", shopId=search["options"][0]["shopId"]
    )
    await client.post(
        f"/voice/calls/{issue_id}/read-backs",
        json={"confirmationId": prepared["confirmationId"], "text": prepared["readBack"]},
    )
    await answer(client, issue_id, prepared["confirmationId"], "Yes.")
    await tool(client, issue_id, "book_repair", shopId=prepared["shopId"])

    result = await tool(client, issue_id, "update_issue", maxBudget=5000)

    assert result == {"error": "issue_already_booked"}


async def test_shops_that_answered_and_failed_the_limits_are_no_vendor(
    client: AsyncClient, issue_id: str
) -> None:
    for name in ALL_SHOPS:
        await set_fault(client, name, "no_open_bay")

    result = await tool(client, issue_id, "search_shops")

    assert result["status"] == "no_vendor"
    assert result["unavailable"] == []


async def test_one_silent_shop_means_the_search_is_not_conclusive(
    client: AsyncClient, issue_id: str
) -> None:
    await set_fault(client, ROCKDALE, "error")
    await set_fault(client, WOODRIDGE, "no_open_bay")

    result = await tool(client, issue_id, "search_shops")

    assert result["status"] == "shops_unavailable"
    assert [shop["name"] for shop in result["unavailable"]] == [ROCKDALE]
    assert {shop["name"] for shop in result["excluded"]} == {WOODRIDGE, MILLRACE}


async def test_an_option_outweighs_a_silent_shop(client: AsyncClient, issue_id: str) -> None:
    await set_fault(client, ROCKDALE, "timeout")

    result = await tool(client, issue_id, "search_shops")

    assert result["status"] == "options_ready"
    assert [option["name"] for option in result["options"]] == [WOODRIDGE]
