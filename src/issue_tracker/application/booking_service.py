from datetime import datetime
from decimal import Decimal
from uuid import UUID

from issue_tracker.application.ports import BookingRepository
from issue_tracker.domain.booking import Booking
from issue_tracker.domain.issue import Issue


class BookingService:
    def __init__(self, repository: BookingRepository) -> None:
        self._repository = repository

    async def book(
        self,
        issue_id: UUID,
        shop_id: UUID,
        confirmed_estimate: Decimal,
        confirmed_start_time: datetime,
    ) -> Booking:
        """Book the estimate and start time the dispatcher agreed to, or raise if they changed."""
        booking = Booking.create(issue_id, shop_id, confirmed_estimate, confirmed_start_time)
        return await self._repository.add(booking)

    async def find_existing(self, issue: Issue) -> Booking | None:
        """Find a booking this issue or its truck already has, even one made on an earlier call,
        which created its own issue. A booked truck can't be booked again, whatever the date."""
        booking = await self._repository.get_for_issue(issue.issue_id)
        if booking is None and issue.truck_id:
            booking = await self._repository.get_for_truck(issue.truck_id)
        return booking
