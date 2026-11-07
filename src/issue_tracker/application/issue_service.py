from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from issue_tracker.application.clock import central_today
from issue_tracker.application.ports import IssueNotFoundError, IssueRepository, TruckRepository
from issue_tracker.domain.issue import Contact, FaultCode, Issue, ProblemType
from issue_tracker.domain.location import Location

# Each listed issue is triaged live, so the list is capped to keep that cost bounded.
ISSUE_LIST_LIMIT = 50


class UnknownTruckError(Exception):
    """No truck has the unit number the client gave, so nothing was saved."""


class NeededByInPastError(Exception):
    """The needed-by date has already passed, so nothing was saved."""


@dataclass(frozen=True, slots=True)
class IssueDetails:
    """What the dispatcher has said so far. Anything not yet known stays None."""

    truck_unit_number: str | None = None
    problem: ProblemType | None = None
    location: Location | None = None
    drivable: bool | None = None
    needed_by: date | None = None
    max_distance_miles: float | None = None
    max_budget: Decimal | None = None
    symptoms: str | None = None
    contact: Contact | None = None
    loaded: bool | None = None
    hazmat: bool | None = None
    odometer_miles: int | None = None
    fault_codes: tuple[FaultCode, ...] | None = None


def _newer[T](new: T | None, old: T | None) -> T | None:
    return new if new is not None else old


def _merge(issue: Issue, details: IssueDetails, truck_id: UUID | None) -> Issue:
    """Apply only the details that have a value, so nothing known is ever cleared."""
    return replace(
        issue,
        truck_id=_newer(truck_id, issue.truck_id),
        problem=_newer(details.problem, issue.problem),
        location=_newer(details.location, issue.location),
        drivable=_newer(details.drivable, issue.drivable),
        needed_by=_newer(details.needed_by, issue.needed_by),
        max_distance_miles=_newer(details.max_distance_miles, issue.max_distance_miles),
        max_budget=_newer(details.max_budget, issue.max_budget),
        symptoms=_newer(details.symptoms, issue.symptoms),
        contact=_newer(details.contact, issue.contact),
        loaded=_newer(details.loaded, issue.loaded),
        hazmat=_newer(details.hazmat, issue.hazmat),
        odometer_miles=_newer(details.odometer_miles, issue.odometer_miles),
        fault_codes=details.fault_codes if details.fault_codes is not None else issue.fault_codes,
    )


class IssueService:
    def __init__(
        self,
        repository: IssueRepository,
        trucks: TruckRepository,
        today: Callable[[], date] = central_today,
    ) -> None:
        self._repository = repository
        self._trucks = trucks
        self._today = today

    async def create_issue(self, details: IssueDetails | None = None) -> Issue:
        details = details or IssueDetails()
        issue = _merge(Issue.create(), details, await self._validate(details))
        await self._repository.add(issue)
        return issue

    async def create_or_get_issue(
        self, details: IssueDetails | None, idempotency_key: str
    ) -> tuple[Issue, bool]:
        """Return the issue for this key, and whether this call created it."""
        # Checked first so a retry returns the original even if its details are no longer valid.
        existing = await self._repository.get_by_key(idempotency_key)
        if existing is not None:
            return existing, False
        details = details or IssueDetails()
        issue = _merge(Issue.create(), details, await self._validate(details))
        stored = await self._repository.add_with_key(issue, idempotency_key)
        return stored, stored.issue_id == issue.issue_id

    async def get_issue(self, issue_id: UUID) -> Issue:
        issue = await self._repository.get(issue_id)
        if issue is None:
            raise IssueNotFoundError
        return issue

    async def list_recent_issues(self) -> list[Issue]:
        return await self._repository.list_recent(ISSUE_LIST_LIMIT)

    async def update_issue(self, issue_id: UUID, details: IssueDetails) -> Issue:
        truck_id = await self._validate(details)
        return await self._repository.update_unless_booked(
            issue_id, lambda issue: _merge(issue, details, truck_id)
        )

    async def _validate(self, details: IssueDetails) -> UUID | None:
        """Reject details that can't be right, returning the ID of the truck they name."""
        if details.needed_by is not None and details.needed_by < self._today():
            raise NeededByInPastError
        if details.truck_unit_number is None:
            return None
        truck = await self._trucks.get_by_unit_number(details.truck_unit_number)
        if truck is None:
            raise UnknownTruckError
        return truck.truck_id
