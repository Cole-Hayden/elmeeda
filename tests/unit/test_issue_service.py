from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from issue_tracker.application.issue_service import IssueDetails, IssueService, UnknownTruckError
from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.truck import Truck

TRUCK = Truck(truck_id=uuid4(), unit_number="214", make="Make", model="Model", year=2021)


class FakeIssueRepository:
    def __init__(self) -> None:
        self.saved: list[Issue] = []

    async def add(self, issue: Issue) -> None:
        self.saved.append(issue)

    async def save(self, issue: Issue) -> None:
        self.saved.append(issue)

    async def get(self, issue_id: UUID) -> Issue | None:
        return next((issue for issue in self.saved if issue.issue_id == issue_id), None)


class FailingIssueRepository:
    async def add(self, issue: Issue) -> None:
        raise StorageUnavailableError

    async def save(self, issue: Issue) -> None:
        raise StorageUnavailableError

    async def get(self, issue_id: UUID) -> Issue | None:
        raise StorageUnavailableError


class FakeTruckRepository:
    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        return TRUCK if unit_number == TRUCK.unit_number else None


async def test_create_issue_saves_and_returns_the_issue() -> None:
    repository = FakeIssueRepository()

    issue = await IssueService(repository, FakeTruckRepository()).create_issue()

    assert repository.saved == [issue]
    assert issue.truck_id is None


async def test_create_issue_generates_distinct_ids() -> None:
    service = IssueService(FakeIssueRepository(), FakeTruckRepository())

    first = await service.create_issue()
    second = await service.create_issue()

    assert first.issue_id != second.issue_id


async def test_create_issue_keeps_the_details_and_resolves_the_truck() -> None:
    repository = FakeIssueRepository()
    details = IssueDetails(
        truck_unit_number="214",
        problem=ProblemType.COOLANT_LEAK,
        max_budget=Decimal("1500.00"),
    )

    issue = await IssueService(repository, FakeTruckRepository()).create_issue(details)

    assert repository.saved == [issue]
    assert issue.truck_id == TRUCK.truck_id
    assert issue.problem is ProblemType.COOLANT_LEAK
    assert issue.max_budget == Decimal("1500.00")


async def test_create_issue_with_an_unknown_truck_saves_nothing() -> None:
    repository = FakeIssueRepository()
    service = IssueService(repository, FakeTruckRepository())

    with pytest.raises(UnknownTruckError):
        await service.create_issue(IssueDetails(truck_unit_number="999"))

    assert repository.saved == []


async def test_create_issue_propagates_storage_failure() -> None:
    service = IssueService(FailingIssueRepository(), FakeTruckRepository())

    with pytest.raises(StorageUnavailableError):
        await service.create_issue()
