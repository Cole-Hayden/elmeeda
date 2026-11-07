from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from issue_tracker.application.issue_service import (
    IssueDetails,
    IssueService,
    NeededByInPastError,
    UnknownTruckError,
)
from issue_tracker.application.ports import (
    IssueBookedError,
    IssueNotFoundError,
    StorageUnavailableError,
)
from issue_tracker.domain.issue import Contact, FaultCode, Issue, ProblemType
from issue_tracker.domain.truck import Truck

TRUCK = Truck(truck_id=uuid4(), unit_number="214", make="Make", model="Model", year=2021)
TODAY = date(2026, 11, 7)


class FakeIssueRepository:
    def __init__(self) -> None:
        self.saved: list[Issue] = []
        self.keys: dict[str, Issue] = {}
        self.booked: set[UUID] = set()

    async def add(self, issue: Issue) -> None:
        self.saved.append(issue)

    async def add_with_key(self, issue: Issue, idempotency_key: str) -> Issue:
        if idempotency_key not in self.keys:
            self.keys[idempotency_key] = issue
            self.saved.append(issue)
        return self.keys[idempotency_key]

    async def get_by_key(self, idempotency_key: str) -> Issue | None:
        return self.keys.get(idempotency_key)

    async def save(self, issue: Issue) -> None:
        self.saved.append(issue)

    async def update_unless_booked(
        self, issue_id: UUID, change: Callable[[Issue], Issue]
    ) -> Issue:
        issue = await self.get(issue_id)
        if issue is None:
            raise IssueNotFoundError
        if issue_id in self.booked:
            raise IssueBookedError
        updated = change(issue)
        self.saved[self.saved.index(issue)] = updated
        return updated

    async def get(self, issue_id: UUID) -> Issue | None:
        return next((issue for issue in self.saved if issue.issue_id == issue_id), None)


class FailingIssueRepository(FakeIssueRepository):
    async def add(self, issue: Issue) -> None:
        raise StorageUnavailableError


class FakeTruckRepository:
    async def get(self, truck_id: UUID) -> Truck | None:
        return TRUCK if truck_id == TRUCK.truck_id else None

    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        return TRUCK if unit_number == TRUCK.unit_number else None


def make_service(repository: FakeIssueRepository) -> IssueService:
    return IssueService(repository, FakeTruckRepository(), lambda: TODAY)


async def test_create_issue_saves_and_returns_the_issue() -> None:
    repository = FakeIssueRepository()

    issue = await make_service(repository).create_issue()

    assert repository.saved == [issue]
    assert issue.truck_id is None


async def test_create_issue_generates_distinct_ids() -> None:
    service = make_service(FakeIssueRepository())

    first = await service.create_issue()
    second = await service.create_issue()

    assert first.issue_id != second.issue_id


async def test_create_issue_keeps_the_details_and_resolves_the_truck() -> None:
    repository = FakeIssueRepository()
    details = IssueDetails(
        truck_unit_number="214",
        problem=ProblemType.COOLANT_LEAK,
        max_budget=Decimal("1500.00"),
        symptoms="Leaking",
        contact=Contact("Dispatch", "555-0100"),
        odometer_miles=1000,
        fault_codes=(FaultCode(110, 0),),
    )

    issue = await make_service(repository).create_issue(details)

    assert repository.saved == [issue]
    assert issue.truck_id == TRUCK.truck_id
    assert issue.problem is ProblemType.COOLANT_LEAK
    assert issue.max_budget == Decimal("1500.00")
    assert issue.symptoms == "Leaking"
    assert issue.contact == Contact("Dispatch", "555-0100")
    assert issue.odometer_miles == 1000
    assert issue.fault_codes == (FaultCode(110, 0),)


async def test_create_issue_with_an_unknown_truck_saves_nothing() -> None:
    repository = FakeIssueRepository()

    with pytest.raises(UnknownTruckError):
        await make_service(repository).create_issue(IssueDetails(truck_unit_number="999"))

    assert repository.saved == []


async def test_create_issue_with_a_past_needed_by_date_saves_nothing() -> None:
    repository = FakeIssueRepository()

    with pytest.raises(NeededByInPastError):
        await make_service(repository).create_issue(IssueDetails(needed_by=date(2026, 11, 6)))

    assert repository.saved == []


async def test_needed_by_today_is_accepted() -> None:
    issue = await make_service(FakeIssueRepository()).create_issue(IssueDetails(needed_by=TODAY))

    assert issue.needed_by == TODAY


async def test_create_issue_propagates_storage_failure() -> None:
    with pytest.raises(StorageUnavailableError):
        await make_service(FailingIssueRepository()).create_issue()


async def test_same_key_returns_the_original_issue_and_ignores_the_new_details() -> None:
    repository = FakeIssueRepository()
    service = make_service(repository)

    first, first_created = await service.create_or_get_issue(
        IssueDetails(symptoms="Original"), "key"
    )
    second, second_created = await service.create_or_get_issue(IssueDetails(symptoms="New"), "key")

    assert (first_created, second_created) == (True, False)
    assert second == first
    assert second.symptoms == "Original"
    assert len(repository.saved) == 1


async def test_retry_returns_the_original_even_if_its_details_are_no_longer_valid() -> None:
    service = make_service(FakeIssueRepository())
    first, _ = await service.create_or_get_issue(IssueDetails(needed_by=TODAY), "key")

    retried, created = await service.create_or_get_issue(
        IssueDetails(needed_by=date(2026, 11, 1)), "key"
    )

    assert retried == first
    assert created is False


async def test_update_changes_only_the_details_sent() -> None:
    repository = FakeIssueRepository()
    original = replace(Issue.create(), symptoms="Leaking", drivable=False, loaded=True)
    await repository.add(original)

    updated = await make_service(repository).update_issue(
        original.issue_id, IssueDetails(drivable=True, truck_unit_number="214")
    )

    assert updated == replace(original, drivable=True, truck_id=TRUCK.truck_id)
    assert await repository.get(original.issue_id) == updated


async def test_update_keeps_false_values_and_can_set_them() -> None:
    repository = FakeIssueRepository()
    original = replace(Issue.create(), drivable=True)
    await repository.add(original)

    updated = await make_service(repository).update_issue(
        original.issue_id, IssueDetails(drivable=False)
    )

    assert updated.drivable is False


async def test_invalid_update_changes_nothing() -> None:
    repository = FakeIssueRepository()
    original = replace(Issue.create(), symptoms="Leaking")
    await repository.add(original)
    service = make_service(repository)

    with pytest.raises(UnknownTruckError):
        await service.update_issue(original.issue_id, IssueDetails(truck_unit_number="999"))
    with pytest.raises(NeededByInPastError):
        await service.update_issue(original.issue_id, IssueDetails(needed_by=date(2026, 1, 1)))

    assert await repository.get(original.issue_id) == original


async def test_get_issue_raises_when_it_does_not_exist() -> None:
    with pytest.raises(IssueNotFoundError):
        await make_service(FakeIssueRepository()).get_issue(uuid4())
