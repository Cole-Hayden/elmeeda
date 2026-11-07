from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.location import Location


@dataclass(frozen=True, slots=True)
class MaintenanceShop:
    """A repair shop. Distance isn't stored because it depends on where the truck is."""

    shop_id: UUID
    name: str
    location: Location
    open_bays: int
    earliest_start: datetime
    # A problem with no estimate is one this shop doesn't repair.
    estimates: Mapping[ProblemType, Decimal] = field(hash=False)

    def estimate_for(self, problem: ProblemType) -> Decimal | None:
        return self.estimates.get(problem)
