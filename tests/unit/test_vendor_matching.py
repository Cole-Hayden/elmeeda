from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from issue_tracker.domain.issue import Issue
from issue_tracker.domain.job import Job, JobPart
from issue_tracker.domain.location import Location
from issue_tracker.domain.maintenance_shop import MaintenanceShop, TowService, VendorCapability
from issue_tracker.domain.truck import Truck
from issue_tracker.domain.vendor_matching import (
    ExcludedVendor,
    ExclusionReason,
    VendorOption,
    calculate_quote,
    evaluate_vendor,
    match_vendors,
)
from issue_tracker.infrastructure.mock_data import (
    COOLANT_LEAK_JOB,
    SCENARIO_ISSUE,
    TRUCK_118,
    TRUCK_214,
    WOODRIDGE_FLEET,
)

DRIVABLE = replace(SCENARIO_ISSUE, drivable=True)
TOWED = replace(SCENARIO_ISSUE, drivable=False, loaded=True, hazmat=False)
JOB = COOLANT_LEAK_JOB
SHOP = WOODRIDGE_FLEET
RATE = Decimal("180.00")


def reason_for(
    shop: MaintenanceShop = SHOP,
    issue: Issue = DRIVABLE,
    truck: Truck = TRUCK_214,
    job: Job | None = JOB,
) -> ExclusionReason | None:
    result = evaluate_vendor(issue, truck, job, shop)
    return result.reason if isinstance(result, ExcludedVendor) else None


def test_vendor_that_passes_every_rule_is_an_option() -> None:
    result = evaluate_vendor(DRIVABLE, TRUCK_214, JOB, SHOP)

    assert isinstance(result, VendorOption)
    assert result.quote.estimate == Decimal("1120.00")


def test_vendor_without_the_job_is_excluded() -> None:
    assert reason_for(replace(SHOP, capabilities={})) is ExclusionReason.JOB_NOT_OFFERED


def test_every_vendor_is_excluded_when_no_job_exists() -> None:
    assert reason_for(job=None) is ExclusionReason.JOB_NOT_OFFERED


def test_vendor_not_authorized_for_the_make_is_excluded() -> None:
    shop = replace(
        SHOP, capabilities={JOB.job_code: VendorCapability(RATE, frozenset({"Volvo"}))}
    )

    assert reason_for(shop) is ExclusionReason.MAKE_NOT_SUPPORTED
    assert reason_for(shop, truck=TRUCK_118) is ExclusionReason.MAKE_NOT_SUPPORTED


def test_vendor_with_no_make_limit_works_on_any_make() -> None:
    assert reason_for(truck=TRUCK_118) is None


def test_vendor_without_a_tow_is_excluded_only_when_one_is_needed() -> None:
    shop = replace(SHOP, tow=None)

    assert reason_for(shop, TOWED) is ExclusionReason.NO_TOW_SERVICE
    assert reason_for(shop, DRIVABLE) is None


def test_vendor_that_cannot_tow_hazmat_is_excluded_only_for_hazmat() -> None:
    shop = replace(SHOP, tow=TowService(Decimal("60.00"), Decimal("4.00"), hazmat=False))

    assert reason_for(shop, replace(TOWED, hazmat=True)) is ExclusionReason.HAZMAT_NOT_SUPPORTED
    assert reason_for(shop, TOWED) is None
    assert reason_for(shop, replace(DRIVABLE, hazmat=True)) is None


def test_vendor_beyond_the_distance_limit_is_excluded() -> None:
    assert reason_for(issue=replace(DRIVABLE, max_distance_miles=5)) is ExclusionReason.TOO_FAR


def test_vendor_above_the_budget_is_excluded() -> None:
    issue = replace(DRIVABLE, max_budget=Decimal("1119.99"))

    assert reason_for(issue=issue) is ExclusionReason.OVER_BUDGET


def test_estimate_equal_to_the_budget_is_not_excluded() -> None:
    assert reason_for(issue=replace(DRIVABLE, max_budget=Decimal("1120.00"))) is None


def test_tow_counts_toward_the_budget() -> None:
    issue = replace(TOWED, max_budget=Decimal("1200.00"))

    assert reason_for(issue=issue) is ExclusionReason.OVER_BUDGET


def test_vendor_with_no_open_bay_is_excluded() -> None:
    assert reason_for(replace(SHOP, open_bays=0)) is ExclusionReason.NO_OPEN_BAY


def test_vendor_that_starts_after_the_needed_by_date_is_excluded() -> None:
    shop = replace(SHOP, earliest_start=SHOP.earliest_start + timedelta(days=1))

    assert reason_for(shop) is ExclusionReason.STARTS_TOO_LATE


def test_vendor_that_starts_on_the_needed_by_date_is_not_excluded() -> None:
    assert SHOP.earliest_start.date() == DRIVABLE.needed_by
    assert reason_for() is None


def test_only_the_first_failed_rule_is_reported() -> None:
    issue = replace(DRIVABLE, max_distance_miles=5, max_budget=Decimal("1.00"))

    assert reason_for(replace(SHOP, open_bays=0), issue) is ExclusionReason.TOO_FAR


def test_rules_are_checked_in_the_documented_order() -> None:
    failing_everything = replace(
        SHOP,
        capabilities={},
        tow=None,
        open_bays=0,
        earliest_start=SHOP.earliest_start + timedelta(days=1),
    )
    issue = replace(TOWED, hazmat=True, max_distance_miles=1, max_budget=Decimal("1.00"))

    assert reason_for(failing_everything, issue) is ExclusionReason.JOB_NOT_OFFERED

    shop = replace(
        failing_everything,
        capabilities={JOB.job_code: VendorCapability(RATE, frozenset({"Volvo"}))},
    )
    assert reason_for(shop, issue) is ExclusionReason.MAKE_NOT_SUPPORTED

    shop = replace(shop, capabilities={JOB.job_code: VendorCapability(RATE)})
    assert reason_for(shop, issue) is ExclusionReason.NO_TOW_SERVICE

    shop = replace(shop, tow=TowService(Decimal("60.00"), Decimal("4.00")))
    assert reason_for(shop, issue) is ExclusionReason.HAZMAT_NOT_SUPPORTED

    shop = replace(shop, tow=TowService(Decimal("60.00"), Decimal("4.00"), hazmat=True))
    assert reason_for(shop, issue) is ExclusionReason.TOO_FAR

    issue = replace(issue, max_distance_miles=100)
    assert reason_for(shop, issue) is ExclusionReason.OVER_BUDGET

    issue = replace(issue, max_budget=Decimal("5000.00"))
    assert reason_for(shop, issue) is ExclusionReason.NO_OPEN_BAY

    shop = replace(shop, open_bays=1)
    assert reason_for(shop, issue) is ExclusionReason.STARTS_TOO_LATE


def test_quote_breaks_down_labor_parts_and_tow() -> None:
    towed = calculate_quote(TOWED, JOB, VendorCapability(RATE), SHOP)

    assert towed.labor == Decimal("720.00")
    assert towed.parts == Decimal("400.00")
    assert towed.tow == Decimal("137.09")
    assert towed.estimate == Decimal("1257.09")


def test_quote_without_a_tow_has_no_tow_fee() -> None:
    quote = calculate_quote(DRIVABLE, JOB, VendorCapability(RATE), SHOP)

    assert quote.tow == Decimal("0.00")
    assert quote.estimate == Decimal("1120.00")


def test_quote_multiplies_part_quantity_by_price() -> None:
    job = replace(JOB, parts=(JobPart("A", "A", 3, Decimal("10.50")),), labor_hours=Decimal("0"))

    assert calculate_quote(DRIVABLE, job, VendorCapability(RATE), SHOP).parts == Decimal("31.50")


def test_quote_rounds_half_cents_up() -> None:
    job = replace(JOB, labor_hours=Decimal("0.1"), parts=())

    quote = calculate_quote(DRIVABLE, job, VendorCapability(Decimal("0.25")), SHOP)

    assert quote.labor == Decimal("0.03")


def test_quote_needs_a_location_and_a_shop_that_tows() -> None:
    with pytest.raises(ValueError):
        calculate_quote(
            replace(DRIVABLE, location=None), JOB, VendorCapability(RATE), SHOP
        )
    with pytest.raises(ValueError):
        calculate_quote(TOWED, JOB, VendorCapability(RATE), replace(SHOP, tow=None))


def test_incomplete_issue_cannot_be_evaluated() -> None:
    with pytest.raises(ValueError):
        evaluate_vendor(replace(DRIVABLE, max_budget=None), TRUCK_214, JOB, SHOP)


def make_option_shop(name: str, hours_later: int, rate: str) -> MaintenanceShop:
    return replace(
        SHOP,
        shop_id=uuid4(),
        name=name,
        location=Location("Nearby", 41.5, -88.2),
        earliest_start=SHOP.earliest_start + timedelta(hours=hours_later),
        capabilities={JOB.job_code: VendorCapability(Decimal(rate))},
    )


def test_options_are_sorted_by_start_then_estimate_then_name() -> None:
    later = make_option_shop("Later", 1, "100.00")
    pricier = make_option_shop("Pricier", 0, "150.00")
    cheaper_b = make_option_shop("Cheaper B", 0, "100.00")
    cheaper_a = make_option_shop("Cheaper A", 0, "100.00")

    options, excluded = match_vendors(
        DRIVABLE, TRUCK_214, JOB, [later, pricier, cheaper_b, cheaper_a]
    )

    assert [option.shop.name for option in options] == [
        "Cheaper A",
        "Cheaper B",
        "Pricier",
        "Later",
    ]
    assert excluded == []


def test_every_vendor_is_either_offered_or_excluded() -> None:
    too_busy = replace(SHOP, shop_id=uuid4(), name="Busy", open_bays=0)

    options, excluded = match_vendors(DRIVABLE, TRUCK_214, JOB, [SHOP, too_busy])

    assert [option.shop for option in options] == [SHOP]
    assert excluded == [ExcludedVendor(too_busy, ExclusionReason.NO_OPEN_BAY)]
