from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from issue_tracker.application.booking_service import BookingService
from issue_tracker.domain.booking import BOOKING_ID_ALPHABET, Booking


class FakeBookingRepository:
    def __init__(self) -> None:
        self.saved: list[Booking] = []

    async def add(self, booking: Booking) -> Booking:
        self.saved.append(booking)
        return booking

    async def get(self, booking_id: str) -> Booking | None:
        return next((b for b in self.saved if b.booking_id == booking_id), None)

    async def get_for_issue(self, issue_id: UUID) -> Booking | None:
        return next((b for b in self.saved if b.issue_id == issue_id), None)

    async def get_for_truck(self, truck_id: UUID) -> Booking | None:
        return None


def make_booking() -> Booking:
    return Booking.create(uuid4(), uuid4(), Decimal("1120.00"), datetime(2026, 11, 7, tzinfo=UTC))


def test_booking_id_is_short_and_has_no_confusable_characters() -> None:
    booking_id = make_booking().booking_id

    assert booking_id.startswith("BK-")
    assert len(booking_id) == 9
    assert set(booking_id.removeprefix("BK-")) <= set(BOOKING_ID_ALPHABET)
    assert not set("01ILO") & set(BOOKING_ID_ALPHABET)


async def test_book_saves_exactly_what_the_dispatcher_confirmed() -> None:
    repository = FakeBookingRepository()
    issue_id, shop_id = uuid4(), uuid4()
    start_time = datetime(2026, 11, 7, 19, tzinfo=UTC)

    booking = await BookingService(repository).book(
        issue_id, shop_id, Decimal("1120.00"), start_time
    )

    assert repository.saved == [booking]
    assert (booking.issue_id, booking.shop_id) == (issue_id, shop_id)
    assert (booking.estimate, booking.start_time) == (Decimal("1120.00"), start_time)
