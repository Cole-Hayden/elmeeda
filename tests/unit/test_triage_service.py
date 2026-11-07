from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from issue_tracker.application.triage_service import TriageService, TriageStatus
from issue_tracker.domain.booking import Booking
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.job import Job
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.domain.truck import Truck
from issue_tracker.infrastructure.mock_data import (
    COOLANT_LEAK_JOB,
    JOBS,
    SCENARIO_ISSUE,
    SHOPS,
    TRUCK_214,
)

READY = replace(SCENARIO_ISSUE, drivable=True)


class FakeTrucks:
    async def get(self, truck_id: UUID) -> Truck | None:
        return TRUCK_214 if truck_id == TRUCK_214.truck_id else None

    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        return TRUCK_214 if unit_number == TRUCK_214.unit_number else None


class FakeJobs:
    def __init__(self, jobs: tuple[Job, ...] = JOBS) -> None:
        self.jobs = jobs

    async def list_for_problem(self, problem: ProblemType) -> list[Job]:
        return [job for job in self.jobs if job.problem is problem]


class FakeShops:
    def __init__(self, shops: tuple[MaintenanceShop, ...] = SHOPS) -> None:
        self.shops = shops

    async def list_all(self) -> list[MaintenanceShop]:
        return list(self.shops)


class FakeBookings:
    def __init__(self, booked: Booking | None = None) -> None:
        self.booked = booked

    async def add(self, booking: Booking) -> Booking:
        return booking

    async def get(self, booking_id: str) -> Booking | None:
        return self.booked

    async def get_for_issue(self, issue_id: UUID) -> Booking | None:
        return self.booked


def make_service(
    shops: tuple[MaintenanceShop, ...] = SHOPS,
    booked: Booking | None = None,
    jobs: tuple[Job, ...] = JOBS,
) -> TriageService:
    return TriageService(FakeTrucks(), FakeJobs(jobs), FakeShops(shops), FakeBookings(booked))


async def test_missing_details_report_needs_info_with_no_vendors() -> None:
    result = await make_service().triage(SCENARIO_ISSUE)

    assert result.status is TriageStatus.NEEDS_INFO
    assert result.options == ()
    assert result.excluded == ()


async def test_job_is_shown_as_soon_as_problem_and_truck_are_known() -> None:
    partial = Issue(
        issue_id=uuid4(), truck_id=TRUCK_214.truck_id, problem=ProblemType.COOLANT_LEAK
    )

    result = await make_service().triage(partial)

    assert result.status is TriageStatus.NEEDS_INFO
    assert result.job == COOLANT_LEAK_JOB


async def test_blank_issue_has_no_truck_or_job() -> None:
    result = await make_service().triage(Issue.create())

    assert result.truck is None
    assert result.job is None


async def test_qualifying_vendor_reports_options_ready() -> None:
    result = await make_service().triage(READY)

    assert result.status is TriageStatus.OPTIONS_READY
    assert [option.shop.name for option in result.options] == [
        "Woodridge Fleet Service",
        "Rockdale Junction Truck Care",
    ]
    assert [(vendor.shop.name, vendor.reason.value) for vendor in result.excluded] == [
        ("Millrace Diesel Works", "over_budget")
    ]


async def test_no_qualifying_vendor_reports_no_vendor() -> None:
    result = await make_service().triage(replace(READY, max_budget=Decimal("1.00")))

    assert result.status is TriageStatus.NO_VENDOR
    assert result.options == ()
    assert len(result.excluded) == 3


async def test_missing_catalog_job_excludes_every_vendor_rather_than_failing() -> None:
    result = await make_service(jobs=()).triage(READY)

    assert result.status is TriageStatus.NO_VENDOR
    assert result.job is None
    assert {vendor.reason.value for vendor in result.excluded} == {"job_not_offered"}


async def test_booked_issue_reports_booked_with_no_options() -> None:
    booking = Booking.create(READY.issue_id, uuid4(), Decimal("1.00"), datetime(2026, 11, 7))

    result = await make_service(booked=booking).triage(READY)

    assert result.status is TriageStatus.BOOKED
    assert result.options == ()
    assert result.excluded == ()
