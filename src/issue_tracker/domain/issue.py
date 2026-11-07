from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from issue_tracker.domain.location import Location


class ProblemType(StrEnum):
    COOLANT_LEAK = "coolant_leak"
    TIRE_BLOWOUT = "tire_blowout"
    BRAKE_FAILURE = "brake_failure"


@dataclass(frozen=True, slots=True)
class Issue:
    """A breakdown, filled in as the dispatcher provides details.

    Details are optional because a call starts with whatever the dispatcher says first.
    The location lives here, not on Truck, because it is where this breakdown happened.
    """

    issue_id: UUID
    truck_id: UUID | None = None
    problem: ProblemType | None = None
    location: Location | None = None
    drivable: bool | None = None
    needed_by: date | None = None
    max_distance_miles: float | None = None
    max_budget: Decimal | None = None

    @classmethod
    def create(cls) -> Self:
        return cls(issue_id=uuid4())

    def missing_details(self) -> tuple[str, ...]:
        """Names of the details the agent still has to ask for before searching."""
        details = {
            "truck_id": self.truck_id,
            "problem": self.problem,
            "location": self.location,
            "drivable": self.drivable,
            "needed_by": self.needed_by,
            "max_distance_miles": self.max_distance_miles,
            "max_budget": self.max_budget,
        }
        return tuple(name for name, value in details.items() if value is None)
