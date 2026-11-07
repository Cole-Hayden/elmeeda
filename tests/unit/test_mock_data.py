from dataclasses import replace
from decimal import Decimal

import pytest

from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.job import select_job
from issue_tracker.domain.location import Location
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.domain.vendor_matching import Quote, calculate_quote
from issue_tracker.infrastructure.mock_data import (
    BRAKE_FAILURE_JOB,
    DIAGNOSTIC_JOB,
    JOBS,
    MILLRACE_DIESEL,
    ROCKDALE_JUNCTION,
    SCENARIO_DAY,
    SCENARIO_ISSUE,
    SHOPS,
    TIRE_BLOWOUT_JOB,
    TRUCK_214,
    TRUCKS,
    WOODRIDGE_FLEET,
)

BEFORE_ANY_ANSWER = (
    "truck_id",
    "problem",
    "location",
    "drivable",
    "needed_by",
    "max_distance_miles",
    "max_budget",
    "symptoms",
    "contact",
)


def quote(shop: MaintenanceShop, problem: ProblemType, drivable: bool = True) -> Quote:
    issue = replace(SCENARIO_ISSUE, problem=problem, drivable=drivable)
    job = select_job(JOBS, problem, TRUCK_214)
    assert job is not None
    capability = shop.capability_for(job.job_code)
    assert capability is not None
    return calculate_quote(issue, job, capability, shop)


def test_new_issue_is_missing_every_detail() -> None:
    assert Issue.create().missing_details() == BEFORE_ANY_ANSWER


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
    assert len({job.job_code for job in JOBS}) == len(JOBS)


def test_every_problem_has_a_generic_job() -> None:
    for problem in ProblemType:
        job = select_job(JOBS, problem, TRUCK_214)
        assert job is not None
        assert job.make is None and job.engine is None


def test_scenario_has_three_shops_all_open_today_and_in_range() -> None:
    assert SCENARIO_ISSUE.location is not None
    assert SCENARIO_ISSUE.max_distance_miles is not None
    assert len(SHOPS) == 3
    for shop in SHOPS:
        assert shop.open_bays > 0
        assert shop.earliest_start.date() == SCENARIO_DAY
        distance = SCENARIO_ISSUE.location.miles_to(shop.location)
        assert distance <= SCENARIO_ISSUE.max_distance_miles


@pytest.mark.parametrize(
    ("shop", "problem", "estimate"),
    [
        (ROCKDALE_JUNCTION, ProblemType.COOLANT_LEAK, "1380.00"),
        (ROCKDALE_JUNCTION, ProblemType.TIRE_BLOWOUT, "640.00"),
        (WOODRIDGE_FLEET, ProblemType.COOLANT_LEAK, "1120.00"),
        (WOODRIDGE_FLEET, ProblemType.TIRE_BLOWOUT, "580.00"),
        (MILLRACE_DIESEL, ProblemType.COOLANT_LEAK, "1640.00"),
    ],
)
def test_calculated_estimates_match_the_scenario_without_a_tow(
    shop: MaintenanceShop, problem: ProblemType, estimate: str
) -> None:
    assert quote(shop, problem).estimate == Decimal(estimate)


@pytest.mark.parametrize(
    ("shop", "labor_and_parts"),
    [(WOODRIDGE_FLEET, "1450.00"), (MILLRACE_DIESEL, "1725.00")],
)
def test_brake_estimates_match_the_scenario_before_their_tow(
    shop: MaintenanceShop, labor_and_parts: str
) -> None:
    # Failed brakes always need a tow, so the labor and parts are checked without it.
    brake_quote = quote(shop, ProblemType.BRAKE_FAILURE)

    assert brake_quote.labor + brake_quote.parts == Decimal(labor_and_parts)
    assert brake_quote.tow > 0


@pytest.mark.parametrize(
    ("shop", "tow", "estimate"),
    [
        (ROCKDALE_JUNCTION, "77.19", "1457.19"),
        (WOODRIDGE_FLEET, "137.09", "1257.09"),
        (MILLRACE_DIESEL, "111.34", "1751.34"),
    ],
)
def test_calculated_estimates_match_the_design_with_a_tow(
    shop: MaintenanceShop, tow: str, estimate: str
) -> None:
    towed = quote(shop, ProblemType.COOLANT_LEAK, drivable=False)

    assert towed.tow == Decimal(tow)
    assert towed.estimate == Decimal(estimate)


@pytest.mark.parametrize("drivable", [True, False])
def test_only_millrace_is_over_budget_for_the_coolant_leak(drivable: bool) -> None:
    assert SCENARIO_ISSUE.max_budget == Decimal("1500.00")
    over_budget = [
        shop
        for shop in SHOPS
        if quote(shop, ProblemType.COOLANT_LEAK, drivable).estimate > Decimal("1500.00")
    ]

    assert over_budget == [MILLRACE_DIESEL]


def test_scenario_shops_trade_off_distance_cost_and_start_time() -> None:
    location = SCENARIO_ISSUE.location
    assert location is not None

    assert location.miles_to(ROCKDALE_JUNCTION.location) < location.miles_to(
        WOODRIDGE_FLEET.location
    )
    assert WOODRIDGE_FLEET.earliest_start < ROCKDALE_JUNCTION.earliest_start
    assert quote(WOODRIDGE_FLEET, ProblemType.COOLANT_LEAK).estimate == Decimal("1120.00")


def test_shop_without_a_capability_does_not_do_that_job() -> None:
    assert MILLRACE_DIESEL.capability_for(TIRE_BLOWOUT_JOB.job_code) is None
    assert ROCKDALE_JUNCTION.capability_for(BRAKE_FAILURE_JOB.job_code) is None


def test_every_shop_offers_diagnosis_at_its_coolant_leak_rate() -> None:
    coolant_job = select_job(JOBS, ProblemType.COOLANT_LEAK, TRUCK_214)
    assert coolant_job is not None
    for shop in SHOPS:
        diagnostic = shop.capability_for(DIAGNOSTIC_JOB.job_code)
        coolant = shop.capability_for(coolant_job.job_code)
        assert diagnostic is not None and coolant is not None
        assert diagnostic.labor_rate == coolant.labor_rate


def test_only_woodridge_tows_hazmat() -> None:
    assert [shop for shop in SHOPS if shop.tow and shop.tow.hazmat] == [WOODRIDGE_FLEET]
