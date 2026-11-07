from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from issue_tracker.domain.location import Location


@dataclass(frozen=True, slots=True)
class VendorCapability:
    """A job a shop does. Null authorized makes means the shop works on any make."""

    labor_rate: Decimal
    authorized_makes: frozenset[str] | None = None

    def works_on(self, make: str) -> bool:
        return self.authorized_makes is None or make in self.authorized_makes


@dataclass(frozen=True, slots=True)
class TowService:
    base_fee: Decimal
    per_mile: Decimal
    hazmat: bool = False


@dataclass(frozen=True, slots=True)
class MaintenanceShop:
    """A repair shop. Distance isn't stored because it depends on where the truck is."""

    shop_id: UUID
    name: str
    location: Location
    open_bays: int
    earliest_start: datetime
    # Keyed by job code. A job with no capability is one this shop doesn't do.
    capabilities: Mapping[str, VendorCapability] = field(hash=False)
    tow: TowService | None = None

    def capability_for(self, job_code: str) -> VendorCapability | None:
        return self.capabilities.get(job_code)
