from datetime import datetime
from decimal import Decimal
from uuid import UUID

from issue_tracker.application.ports import BookingRepository
from issue_tracker.domain.booking import Booking


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
