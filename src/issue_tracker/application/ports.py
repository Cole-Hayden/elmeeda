from enum import StrEnum
from typing import Protocol
from uuid import UUID

from issue_tracker.domain.booking import Booking
from issue_tracker.domain.issue import Issue
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.domain.truck import Truck


class StorageUnavailableError(Exception):
    """The operation could not be completed because storage failed."""


class BookingRejection(StrEnum):
    ISSUE_NOT_FOUND = "issue_not_found"
    ISSUE_INCOMPLETE = "issue_incomplete"
    ISSUE_ALREADY_BOOKED = "issue_already_booked"
    SHOP_NOT_FOUND = "shop_not_found"
    NO_OPEN_BAY = "no_open_bay"
    QUOTE_CHANGED = "quote_changed"


class BookingRejectedError(Exception):
    """Nothing was booked. The reason tells the agent what to say truthfully."""

    def __init__(self, reason: BookingRejection) -> None:
        super().__init__(reason.value)
        self.reason = reason


class IssueRepository(Protocol):
    async def add(self, issue: Issue) -> None:
        """Durably save a new issue, or raise StorageUnavailableError."""
        ...

    async def save(self, issue: Issue) -> None:
        """Durably save the issue's latest details, or raise StorageUnavailableError."""
        ...

    async def get(self, issue_id: UUID) -> Issue | None:
        """Return the issue if it exists, or raise StorageUnavailableError."""
        ...


class TruckRepository(Protocol):
    async def get_by_unit_number(self, unit_number: str) -> Truck | None:
        """Return the truck if it exists, or raise StorageUnavailableError."""
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
