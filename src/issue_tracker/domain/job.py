from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.truck import Truck


@dataclass(frozen=True, slots=True)
class JobPart:
    part_number: str
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class Job:
    """A standard repair. A null make or engine means the job applies to any."""

    job_code: str
    problem: ProblemType
    name: str
    labor_hours: Decimal
    parts: tuple[JobPart, ...] = ()
    make: str | None = None
    engine: str | None = None
    requires_diagnosis: bool = False
    vmrs_code: str | None = None

    def applies_to(self, truck: Truck) -> bool:
        return (self.make is None or self.make == truck.make) and (
            self.engine is None or self.engine == truck.engine
        )


def select_job(jobs: Iterable[Job], problem: ProblemType, truck: Truck) -> Job | None:
    """Return the most specific match: make and engine, then make, then generic."""
    matches = [job for job in jobs if job.problem is problem and job.applies_to(truck)]
    if not matches:
        return None
    return max(matches, key=lambda job: (job.make is not None, job.engine is not None))
