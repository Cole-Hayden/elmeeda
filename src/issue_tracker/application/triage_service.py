from dataclasses import dataclass
from enum import StrEnum

from issue_tracker.application.ports import (
    BookingRepository,
    JobRepository,
    MaintenanceShopRepository,
    TruckRepository,
)
from issue_tracker.application.shop_checks import ShopChecker, UnavailableShop
from issue_tracker.domain.issue import Issue
from issue_tracker.domain.job import Job, select_job
from issue_tracker.domain.truck import Truck
from issue_tracker.domain.vendor_matching import ExcludedVendor, VendorOption, match_vendors


class TriageStatus(StrEnum):
    NEEDS_INFO = "needs_info"
    OPTIONS_READY = "options_ready"
    NO_VENDOR = "no_vendor"
    SHOPS_UNAVAILABLE = "shops_unavailable"
    BOOKED = "booked"


@dataclass(frozen=True, slots=True)
class TriageResult:
    issue: Issue
    status: TriageStatus
    truck: Truck | None
    job: Job | None
    options: tuple[VendorOption, ...] = ()
    excluded: tuple[ExcludedVendor, ...] = ()
    unavailable: tuple[UnavailableShop, ...] = ()


class TriageService:
    """Works out an issue's state from current data. Nothing here is stored on the issue,
    because prices, bays, and start times can change between reads.

    With a checker, each shop is asked for its current state and may fail on its own."""

    def __init__(
        self,
        trucks: TruckRepository,
        jobs: JobRepository,
        shops: MaintenanceShopRepository,
        bookings: BookingRepository,
        checker: ShopChecker | None = None,
    ) -> None:
        self._trucks = trucks
        self._jobs = jobs
        self._shops = shops
        self._bookings = bookings
        self._checker = checker

    async def triage(self, issue: Issue, *, check_shops: bool = True) -> TriageResult:
        truck = await self._trucks.get(issue.truck_id) if issue.truck_id else None
        job = None
        if issue.problem is not None and truck is not None:
            job = select_job(await self._jobs.list_for_problem(issue.problem), issue.problem, truck)

        if await self._bookings.get_for_issue(issue.issue_id) is not None:
            return TriageResult(issue, TriageStatus.BOOKED, truck, job)
        if truck is None or issue.missing_details():
            return TriageResult(issue, TriageStatus.NEEDS_INFO, truck, job)

        shops = await self._shops.list_all()
        unavailable: list[UnavailableShop] = []
        if self._checker is not None and check_shops:
            shops, unavailable = await self._checker.check_all(shops)
        options, excluded = match_vendors(issue, truck, job, shops)
        # A shop that gave no answer might still qualify, so "no vendor" would be a guess.
        if options:
            status = TriageStatus.OPTIONS_READY
        elif unavailable:
            status = TriageStatus.SHOPS_UNAVAILABLE
        else:
            status = TriageStatus.NO_VENDOR
        return TriageResult(
            issue, status, truck, job, tuple(options), tuple(excluded), tuple(unavailable)
        )
