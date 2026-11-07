from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from issue_tracker.application.ports import IssueRepository, TruckRepository
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.location import Location


class UnknownTruckError(Exception):
    """No truck has the unit number the client gave, so the issue was not created."""


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


class IssueService:
    def __init__(self, repository: IssueRepository, trucks: TruckRepository) -> None:
        self._repository = repository
        self._trucks = trucks

    async def create_issue(self, details: IssueDetails | None = None) -> Issue:
        details = details or IssueDetails()
        truck_id = None
        if details.truck_unit_number is not None:
            truck = await self._trucks.get_by_unit_number(details.truck_unit_number)
            if truck is None:
                raise UnknownTruckError
            truck_id = truck.truck_id

        issue = replace(
            Issue.create(),
            truck_id=truck_id,
            problem=details.problem,
            location=details.location,
            drivable=details.drivable,
            needed_by=details.needed_by,
            max_distance_miles=details.max_distance_miles,
            max_budget=details.max_budget,
        )
        await self._repository.add(issue)
        return issue
