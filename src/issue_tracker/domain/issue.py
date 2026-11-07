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
    # The problem doesn't fit a known type, so a shop has to diagnose it.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Contact:
    name: str
    phone: str


@dataclass(frozen=True, slots=True)
class FaultCode:
    """A J1939 fault: the SPN says what failed and the FMI says how."""

    spn: int
    fmi: int


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
    symptoms: str | None = None
    contact: Contact | None = None
    loaded: bool | None = None
    hazmat: bool | None = None
    odometer_miles: int | None = None
    fault_codes: tuple[FaultCode, ...] = ()

    @classmethod
    def create(cls) -> Self:
        return cls(issue_id=uuid4())

    @property
    def tow_required(self) -> bool:
        """Failed brakes need a tow whatever the driver says, because driving isn't safe."""
        return self.drivable is False or self.problem is ProblemType.BRAKE_FAILURE

    def missing_details(self) -> tuple[str, ...]:
        """Names of the details the agent still has to ask for before searching."""
        details: dict[str, object] = {
            "truck_id": self.truck_id,
            "problem": self.problem,
            "location": self.location,
            "drivable": self.drivable,
            "needed_by": self.needed_by,
            "max_distance_miles": self.max_distance_miles,
            "max_budget": self.max_budget,
            "symptoms": self.symptoms,
        }
        if self.tow_required:
            details |= {"loaded": self.loaded, "hazmat": self.hazmat}
        return tuple(name for name, value in details.items() if value is None)
