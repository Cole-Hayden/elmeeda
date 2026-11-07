from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from issue_tracker.domain.issue import Issue
from issue_tracker.domain.job import Job
from issue_tracker.domain.maintenance_shop import MaintenanceShop, VendorCapability
from issue_tracker.domain.truck import Truck

CENTS = Decimal("0.01")


class ExclusionReason(StrEnum):
    JOB_NOT_OFFERED = "job_not_offered"
    MAKE_NOT_SUPPORTED = "make_not_supported"
    NO_TOW_SERVICE = "no_tow_service"
    HAZMAT_NOT_SUPPORTED = "hazmat_not_supported"
    TOO_FAR = "too_far"
    OVER_BUDGET = "over_budget"
    NO_OPEN_BAY = "no_open_bay"
    STARTS_TOO_LATE = "starts_too_late"


@dataclass(frozen=True, slots=True)
class Quote:
    labor: Decimal
    parts: Decimal
    tow: Decimal
    estimate: Decimal


@dataclass(frozen=True, slots=True)
class VendorOption:
    shop: MaintenanceShop
    distance_miles: float
    quote: Quote


@dataclass(frozen=True, slots=True)
class ExcludedVendor:
    shop: MaintenanceShop
    reason: ExclusionReason


def _to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def check_capability(
    job: Job | None, truck: Truck, shop: MaintenanceShop
) -> ExclusionReason | None:
    """Rules about the work itself, which booking also has to respect."""
    capability = shop.capability_for(job.job_code) if job else None
    if capability is None:
        return ExclusionReason.JOB_NOT_OFFERED
    if not capability.works_on(truck.make):
        return ExclusionReason.MAKE_NOT_SUPPORTED
    return None


def check_tow(issue: Issue, shop: MaintenanceShop) -> ExclusionReason | None:
    """Rules about moving the truck, which booking also has to respect."""
    if not issue.tow_required:
        return None
    if shop.tow is None:
        return ExclusionReason.NO_TOW_SERVICE
    if issue.hazmat and not shop.tow.hazmat:
        return ExclusionReason.HAZMAT_NOT_SUPPORTED
    return None


def calculate_quote(
    issue: Issue, job: Job, capability: VendorCapability, shop: MaintenanceShop
) -> Quote:
    """The one price calculation, shared by offers and bookings so they can't disagree."""
    if issue.location is None:
        raise ValueError("A quote needs the issue's location.")
    labor = _to_cents(job.labor_hours * capability.labor_rate)
    parts = _to_cents(sum((part.quantity * part.unit_price for part in job.parts), Decimal("0")))
    tow = Decimal("0.00")
    if issue.tow_required:
        if shop.tow is None:
            raise ValueError("A quote with a tow needs a shop that tows.")
        miles = Decimal(str(issue.location.miles_to(shop.location)))
        tow = _to_cents(shop.tow.base_fee + shop.tow.per_mile * miles)
    return Quote(labor=labor, parts=parts, tow=tow, estimate=labor + parts + tow)


def evaluate_vendor(
    issue: Issue, truck: Truck, job: Job | None, shop: MaintenanceShop
) -> VendorOption | ExcludedVendor:
    """Apply the rules in order, returning an option or the first reason the shop fails."""
    if (
        issue.location is None
        or issue.max_distance_miles is None
        or issue.max_budget is None
        or issue.needed_by is None
    ):
        raise ValueError("Vendors can only be evaluated for a complete issue.")

    reason = check_capability(job, truck, shop) or check_tow(issue, shop)
    if reason is not None:
        return ExcludedVendor(shop, reason)
    assert job is not None  # check_capability rejected a missing job.
    capability = shop.capability_for(job.job_code)
    assert capability is not None  # check_capability rejected a missing capability.

    distance = issue.location.miles_to(shop.location)
    if distance > issue.max_distance_miles:
        return ExcludedVendor(shop, ExclusionReason.TOO_FAR)
    quote = calculate_quote(issue, job, capability, shop)
    if quote.estimate > issue.max_budget:
        return ExcludedVendor(shop, ExclusionReason.OVER_BUDGET)
    if shop.open_bays < 1:
        return ExcludedVendor(shop, ExclusionReason.NO_OPEN_BAY)
    if shop.earliest_start.date() > issue.needed_by:
        return ExcludedVendor(shop, ExclusionReason.STARTS_TOO_LATE)
    return VendorOption(shop, distance, quote)


def match_vendors(
    issue: Issue, truck: Truck, job: Job | None, shops: Iterable[MaintenanceShop]
) -> tuple[list[VendorOption], list[ExcludedVendor]]:
    options: list[VendorOption] = []
    excluded: list[ExcludedVendor] = []
    for shop in shops:
        result = evaluate_vendor(issue, truck, job, shop)
        if isinstance(result, VendorOption):
            options.append(result)
        else:
            excluded.append(result)
    options.sort(
        key=lambda option: (option.shop.earliest_start, option.quote.estimate, option.shop.name)
    )
    return options, excluded
