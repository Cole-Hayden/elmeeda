from decimal import Decimal

import pytest

from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.infrastructure.mock_data import (
    MILLRACE_DIESEL,
    ROCKDALE_JUNCTION,
    SCENARIO_DAY,
    SCENARIO_ISSUE,
    SHOPS,
    TRUCK_214,
    TRUCKS,
    WOODRIDGE_FLEET,
)


def test_new_issue_is_missing_every_detail() -> None:
    assert Issue.create().missing_details() == (
        "truck_id",
        "problem",
        "location",
        "drivable",
        "needed_by",
        "max_distance_miles",
        "max_budget",
    )


def test_scenario_issue_only_needs_to_ask_if_the_truck_can_be_driven() -> None:
    assert SCENARIO_ISSUE.missing_details() == ("drivable",)
    assert SCENARIO_ISSUE.truck_id == TRUCK_214.truck_id


def test_false_counts_as_answered() -> None:
    issue = Issue.create()
    answered = Issue(issue_id=issue.issue_id, drivable=False)

    assert "drivable" not in answered.missing_details()


def test_miles_to_matches_a_known_distance() -> None:
    # One degree of latitude is about 69 miles.
    start = Location("start", 41.0, -88.0)
    end = Location("end", 42.0, -88.0)

    assert start.miles_to(end) == pytest.approx(69.1, abs=0.1)


def test_ids_are_unique() -> None:
    assert len({truck.truck_id for truck in TRUCKS}) == len(TRUCKS)
    assert len({shop.shop_id for shop in SHOPS}) == len(SHOPS)


def test_scenario_has_three_shops_all_open_today_and_in_range() -> None:
    assert SCENARIO_ISSUE.location is not None
    assert SCENARIO_ISSUE.max_distance_miles is not None
    assert len(SHOPS) == 3
    for shop in SHOPS:
        assert shop.open_bays > 0
        assert shop.earliest_start.date() == SCENARIO_DAY
        distance = SCENARIO_ISSUE.location.miles_to(shop.location)
        assert distance <= SCENARIO_ISSUE.max_distance_miles


def test_only_millrace_is_over_budget_for_the_coolant_leak() -> None:
    assert SCENARIO_ISSUE.max_budget == Decimal("1500.00")
    estimates = {shop: shop.estimate_for(ProblemType.COOLANT_LEAK) for shop in SHOPS}
    over_budget = [
        shop for shop, estimate in estimates.items() if estimate and estimate > Decimal("1500.00")
    ]

    assert over_budget == [MILLRACE_DIESEL]


def test_scenario_shops_trade_off_distance_cost_and_start_time() -> None:
    location = SCENARIO_ISSUE.location
    assert location is not None

    assert location.miles_to(ROCKDALE_JUNCTION.location) < location.miles_to(
        WOODRIDGE_FLEET.location
    )
    assert WOODRIDGE_FLEET.earliest_start < ROCKDALE_JUNCTION.earliest_start
    assert WOODRIDGE_FLEET.estimate_for(ProblemType.COOLANT_LEAK) == Decimal("1120.00")


def test_shop_without_an_estimate_does_not_repair_that_problem() -> None:
    assert MILLRACE_DIESEL.estimate_for(ProblemType.TIRE_BLOWOUT) is None
