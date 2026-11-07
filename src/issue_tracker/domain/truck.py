from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Truck:
    truck_id: UUID
    unit_number: str
    make: str
    model: str
    year: int
    vin: str | None = None
    engine: str | None = None
