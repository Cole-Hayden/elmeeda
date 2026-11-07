from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from issue_tracker.application.booking_service import BookingService
from issue_tracker.application.issue_service import IssueDetails, IssueService
from issue_tracker.application.ports import (
    BookingRejectedError,
    BookingRejection,
    ConfirmationRepository,
    LimitChangeRepository,
    MaintenanceShopRepository,
)
from issue_tracker.application.shop_checks import ShopChecker
from issue_tracker.application.triage_service import TriageResult, TriageService, TriageStatus
from issue_tracker.domain.booking import Booking
from issue_tracker.domain.confirmation import (
    ConfirmationAnswer,
    LimitChange,
    PendingLimitChange,
    PreparedBooking,
    classify_answer,
)
from issue_tracker.domain.issue import Issue
from issue_tracker.domain.places import KnownPlace, find_place
from issue_tracker.domain.read_back import read_back_matches
from issue_tracker.domain.vendor_matching import VendorOption


class ShopNotAvailableError(Exception):
    """The shop can't be offered for this issue. The reason, when known, says why."""

    def __init__(self, reason: str | None) -> None:
        super().__init__(reason or "shop_not_available")
        self.reason = reason


class ConfirmationRequiredError(Exception):
    """The dispatcher hasn't said yes to this shop's prepared estimate and time."""


class ReadBackRequiredError(Exception):
    """The agent hasn't finished saying this shop's prepared estimate and time."""


@dataclass(frozen=True, slots=True)
class IssueUpdate:
    triage: TriageResult
    location_unknown: bool
    limit_change: PendingLimitChange | None = None


@dataclass(frozen=True, slots=True)
class ConfirmedBooking:
    booking: Booking
    shop_name: str
    already_booked: bool = False


@dataclass(frozen=True, slots=True)
class ShopSearch:
    triage: TriageResult
    existing: ConfirmedBooking | None


@dataclass(frozen=True, slots=True)
class PreparedOption:
    prepared: PreparedBooking
    shop_name: str


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer: ConfirmationAnswer
    confirmed: bool


def _raised[T: (Decimal, float, date)](new: T | None, old: T | None) -> T | None:
    return new if new is not None and old is not None and new > old else None


def _loosened(issue: Issue, details: IssueDetails) -> LimitChange | None:
    """The limits already set that these details would make easier to meet. Setting a limit for
    the first time, or tightening one, loosens nothing."""
    change = LimitChange(
        max_distance_miles=_raised(details.max_distance_miles, issue.max_distance_miles),
        needed_by=_raised(details.needed_by, issue.needed_by),
        max_budget=_raised(details.max_budget, issue.max_budget),
    )
    return None if change == LimitChange() else change


def _without_change(details: IssueDetails, change: LimitChange) -> IssueDetails:
    return replace(
        details,
        max_distance_miles=None if change.max_distance_miles else details.max_distance_miles,
        needed_by=None if change.needed_by else details.needed_by,
        max_budget=None if change.max_budget else details.max_budget,
    )


class VoiceTools:
    """What the voice agent can do. It doesn't know how tool calls arrive, so a sideband
    connection could replace the browser relay without changing this."""

    def __init__(
        self,
        issues: IssueService,
        triage: TriageService,
        bookings: BookingService,
        confirmations: ConfirmationRepository,
        limit_changes: LimitChangeRepository,
        shops: MaintenanceShopRepository,
        checker: ShopChecker,
        places: Sequence[KnownPlace],
    ) -> None:
        self._issues = issues
        self._triage = triage
        self._bookings = bookings
        self._confirmations = confirmations
        self._limit_changes = limit_changes
        self._shops = shops
        self._checker = checker
        self._places = places

    async def update_issue(
        self, issue_id: UUID, details: IssueDetails, place: str | None
    ) -> IssueUpdate:
        """Save what the dispatcher said. An unknown place doesn't lose the other details, and
        neither does a loosened limit, which waits for the dispatcher's yes to its read-back."""
        location = find_place(place, self._places) if place else None
        details = replace(details, location=location)
        change = _loosened(await self._issues.get_issue(issue_id), details)
        pending = await self._limit_changes.get(issue_id) if change else None
        same_change = pending is not None and pending.change == change
        approved = same_change and pending is not None and pending.confirmed

        if change is not None and not approved:
            details = _without_change(details, change)
        issue = await self._issues.update_issue(issue_id, details)

        waiting = None
        if approved:
            await self._limit_changes.clear(issue_id)
        elif change is not None:
            # Saved after the update, so a booked issue never gets a change to confirm. Asking
            # again for the same change keeps its ID, so a reply still being transcribed counts.
            waiting = pending if same_change else PendingLimitChange(uuid4(), issue_id, change)
            if not same_change and waiting is not None:
                await self._limit_changes.prepare(waiting)
        return IssueUpdate(
            await self._triage.triage(issue, check_shops=False),
            location_unknown=bool(place) and location is None,
            limit_change=waiting,
        )

    async def search_shops(self, issue_id: UUID) -> ShopSearch:
        issue = await self._issues.get_issue(issue_id)
        booking = await self._bookings.find_existing(issue)
        if booking is not None:
            triage = await self._triage.triage(issue, check_shops=False)
            return ShopSearch(
                replace(
                    triage, status=TriageStatus.BOOKED, options=(), excluded=(), unavailable=()
                ),
                await self._existing(booking),
            )
        return ShopSearch(await self._triage.triage(issue), None)

    async def prepare_booking(self, issue_id: UUID, shop_id: UUID) -> PreparedOption:
        """Hold the shop's current quote for the dispatcher to confirm. This books nothing."""
        search = await self.search_shops(issue_id)
        if search.existing is not None:
            raise ShopNotAvailableError("already_booked")
        option = self._find_option(search.triage, shop_id)
        prepared = PreparedBooking(
            confirmation_id=uuid4(),
            issue_id=issue_id,
            shop_id=shop_id,
            estimate=option.quote.estimate,
            start_time=option.shop.earliest_start,
        )
        await self._confirmations.prepare(prepared)
        return PreparedOption(prepared, option.shop.name)

    @staticmethod
    def _find_option(result: TriageResult, shop_id: UUID) -> VendorOption:
        for option in result.options:
            if option.shop.shop_id == shop_id:
                return option
        for excluded in result.excluded:
            if excluded.shop.shop_id == shop_id:
                raise ShopNotAvailableError(excluded.reason.value)
        for unavailable in result.unavailable:
            if unavailable.shop.shop_id == shop_id:
                raise ShopNotAvailableError(unavailable.failure.value)
        raise ShopNotAvailableError(None)

    async def record_read_back(self, issue_id: UUID, confirmation_id: UUID, spoken: str) -> bool:
        """Record what the agent finished saying. Once it has said the prepared shop, estimate,
        and time, a yes can count. Anything else it says doesn't take that back, so "booking that
        now" after the yes can't cancel the booking."""
        prepared = await self._confirmations.get(issue_id)
        if prepared is None or prepared.confirmation_id != confirmation_id:
            return False
        shops = await self._shops.list_all()
        name = next(shop.name for shop in shops if shop.shop_id == prepared.shop_id)
        matched = read_back_matches(spoken, name, prepared.estimate, prepared.start_time)
        if matched:
            await self._confirmations.mark_read_back(issue_id, confirmation_id)
        return matched

    async def record_answer(
        self, issue_id: UUID, confirmation_id: UUID, spoken: str
    ) -> AnswerResult:
        """Record what the dispatcher said in reply. The latest reply decides, so "yes" followed
        by "wait, no" isn't a yes. A reply to an earlier read-back doesn't count, and neither does
        a yes to a booking whose details the agent hasn't said yet."""
        answer = classify_answer(spoken)
        said_yes = answer is ConfirmationAnswer.YES
        prepared = await self._confirmations.get(issue_id)
        if prepared is not None and prepared.confirmation_id == confirmation_id:
            agreed = said_yes and prepared.read_back
            is_current = await self._confirmations.record_answer(
                issue_id, confirmation_id, agreed
            )
            return AnswerResult(answer, is_current and agreed)
        is_current = await self._limit_changes.record_answer(issue_id, confirmation_id, said_yes)
        return AnswerResult(answer, is_current and said_yes)

    async def book_repair(self, issue_id: UUID, shop_id: UUID) -> ConfirmedBooking:
        """Book what the dispatcher confirmed. The estimate and time come from the prepared
        booking, never from the model. Any retry or second "yes" gets the existing booking."""
        issue = await self._issues.get_issue(issue_id)
        prepared = await self._confirmations.get(issue_id)
        # Looked up after the confirmation, because booking clears it only once committed.
        existing = await self._bookings.find_existing(issue)
        if existing is not None:
            return await self._existing(existing)
        if prepared is None or prepared.shop_id != shop_id:
            raise ConfirmationRequiredError
        if not prepared.read_back:
            raise ReadBackRequiredError
        if not prepared.confirmed:
            raise ConfirmationRequiredError

        shop = next(s for s in await self._shops.list_all() if s.shop_id == shop_id)
        # Any outcome ends this confirmation, so trying again needs a new read-back and yes.
        try:
            if (await self._checker.check(shop)).open_bays < 1:
                raise BookingRejectedError(BookingRejection.NO_OPEN_BAY)
            booking = await self._bookings.book(
                issue_id, shop_id, prepared.estimate, prepared.start_time
            )
        except BookingRejectedError as exc:
            found = await self._bookings.find_existing(issue)
            if exc.reason is BookingRejection.TRUCK_ALREADY_BOOKED and found is not None:
                return await self._existing(found)
            raise
        finally:
            await self._confirmations.clear(issue_id)
        return ConfirmedBooking(booking, shop.name)

    async def _existing(self, booking: Booking) -> ConfirmedBooking:
        shops = await self._shops.list_all()
        name = next(shop.name for shop in shops if shop.shop_id == booking.shop_id)
        return ConfirmedBooking(booking, name, already_booked=True)
