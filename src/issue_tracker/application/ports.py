from collections.abc import Callable
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from issue_tracker.domain.booking import Booking
from issue_tracker.domain.confirmation import PendingLimitChange, PreparedBooking
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.job import Job
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.domain.truck import Truck


class StorageUnavailableError(Exception):
    """The operation could not be completed because storage failed."""


class IssueNotFoundError(Exception):
    """No issue has that ID."""


class IssueBookedError(Exception):
    """The issue has a booking, so its details can no longer change."""


class BookingRejection(StrEnum):
    ISSUE_NOT_FOUND = "issue_not_found"
    ISSUE_INCOMPLETE = "issue_incomplete"
    ISSUE_ALREADY_BOOKED = "issue_already_booked"
    SHOP_NOT_FOUND = "shop_not_found"
    JOB_NOT_OFFERED = "job_not_offered"
    NO_OPEN_BAY = "no_open_bay"
    QUOTE_CHANGED = "quote_changed"
    TRUCK_ALREADY_BOOKED = "truck_already_booked"


class BookingRejectedError(Exception):
    """Nothing was booked. The reason tells the agent what to say truthfully."""

    def __init__(self, reason: BookingRejection) -> None:
        super().__init__(reason.value)
        self.reason = reason


class IssueRepository(Protocol):
    async def add(self, issue: Issue) -> None:
        """Durably save a new issue, or raise StorageUnavailableError."""
        ...

    async def add_with_key(self, issue: Issue, idempotency_key: str) -> Issue:
        """Save the issue unless the key already has one, and return the issue the key holds.

        Safe when requests with the same key run concurrently. Raises StorageUnavailableError.
        """
        ...

    async def get_by_key(self, idempotency_key: str) -> Issue | None:
        """Return the issue created with this key, or raise StorageUnavailableError."""
        ...

    async def save(self, issue: Issue) -> None:
        """Durably save the issue's latest details, or raise StorageUnavailableError."""
        ...

    async def update_unless_booked(
        self, issue_id: UUID, change: Callable[[Issue], Issue]
    ) -> Issue:
        """Atomically apply the change, returning the updated issue.

        Raises IssueNotFoundError, IssueBookedError, or StorageUnavailableError.
        """
        ...

    async def get(self, issue_id: UUID) -> Issue | None:
        """Return the issue if it exists, or raise StorageUnavailableError."""
        ...


class TruckRepository(Protocol):
    async def get(self, truck_id: UUID) -> Truck | None:
        """Return the truck if it exists, or raise StorageUnavailableError."""
        ...

    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        """Return the truck if it exists, or raise StorageUnavailableError."""
        ...


class JobRepository(Protocol):
    async def list_for_problem(self, problem: ProblemType) -> list[Job]:
        """Return every job variant for the problem, or raise StorageUnavailableError."""
        ...


class MaintenanceShopRepository(Protocol):
    async def list_all(self) -> list[MaintenanceShop]:
        """Return every shop's current state, or raise StorageUnavailableError."""
        ...


class BookingRepository(Protocol):
    async def add(self, booking: Booking) -> Booking:
        """Atomically take a bay and save the booking, returning the booking that was stored.

        Retrying for the same issue and shop returns the original booking. Raises
        BookingRejectedError if it cannot be booked, or StorageUnavailableError.
        """
        ...

    async def get(self, booking_id: str) -> Booking | None:
        """Return the booking if it exists, or raise StorageUnavailableError."""
        ...

    async def get_for_issue(self, issue_id: UUID) -> Booking | None:
        """Return the issue's booking if it has one, or raise StorageUnavailableError."""
        ...

    async def get_for_truck(self, truck_id: UUID) -> Booking | None:
        """Return the truck's booking if it has one, or raise StorageUnavailableError."""
        ...


class ConfirmationRepository(Protocol):
    async def prepare(self, prepared: PreparedBooking) -> None:
        """Replace the issue's prepared booking, unconfirmed, or raise StorageUnavailableError."""
        ...

    async def get(self, issue_id: UUID) -> PreparedBooking | None:
        """Return the issue's prepared booking, or raise StorageUnavailableError."""
        ...

    async def mark_read_back(self, issue_id: UUID, confirmation_id: UUID) -> None:
        """Note that the agent said that prepared booking's details, if it's still the current
        one, or raise StorageUnavailableError."""
        ...

    async def record_answer(self, issue_id: UUID, confirmation_id: UUID, confirmed: bool) -> bool:
        """Set whether that prepared booking is confirmed, returning False if it's no longer the
        current one. Raises StorageUnavailableError."""
        ...

    async def clear(self, issue_id: UUID) -> None:
        """Forget the issue's prepared booking, or raise StorageUnavailableError."""
        ...


class LimitChangeRepository(Protocol):
    async def prepare(self, pending: PendingLimitChange) -> None:
        """Replace the issue's pending change, unconfirmed, or raise StorageUnavailableError."""
        ...

    async def get(self, issue_id: UUID) -> PendingLimitChange | None:
        """Return the issue's pending change, or raise StorageUnavailableError."""
        ...

    async def record_answer(self, issue_id: UUID, confirmation_id: UUID, confirmed: bool) -> bool:
        """Set whether that pending change is confirmed, returning False if it's no longer the
        current one. Raises StorageUnavailableError."""
        ...

    async def clear(self, issue_id: UUID) -> None:
        """Forget the issue's pending change, or raise StorageUnavailableError."""
        ...
