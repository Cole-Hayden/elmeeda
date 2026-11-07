import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ConfirmationAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class PreparedBooking:
    """The exact shop, estimate, and time read back to the dispatcher."""

    confirmation_id: UUID
    issue_id: UUID
    shop_id: UUID
    estimate: Decimal
    start_time: datetime
    confirmed: bool = False
    read_back: bool = False


@dataclass(frozen=True, slots=True)
class LimitChange:
    """The limits the model asked to loosen. A limit staying as it is stays None."""

    max_distance_miles: float | None = None
    needed_by: date | None = None
    max_budget: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PendingLimitChange:
    """A loosened limit read back to the dispatcher, which isn't saved until they say yes."""

    confirmation_id: UUID
    issue_id: UUID
    change: LimitChange
    confirmed: bool = False


_YES = re.compile(
    r"\b(yes|yeah|yep|yup|correct|confirm|confirmed|affirmative|go ahead|book it|book that|"
    r"book this|book the repair|do it|go for it|that works|works for me|that's right|thats right|"
    r"sounds good|sounds great|please do|proceed|absolutely|definitely|of course)\b"
)
# These often just mean "I'm listening", so they only count as a whole short reply. "Okay" is a
# yes, and "Okay, let me think" isn't.
_SHORT_YES = re.compile(r"\b(sure|ok|okay|right|fine|perfect|great|good|let's go|lets go)\b")
_SHORT_REPLY_WORDS = 3
# Friendly phrases that contain a negative word but don't mean no.
_NOT_NEGATIVE = re.compile(r"\b(no problem|not a problem|no worries|why not)\b")
_NO = re.compile(
    r"\b(no|nope|not|don't|dont|wait|hold|hang|stop|cancel|actually|instead|change|different|"
    r"other|another|but)\b"
    r"|n't\b"
)
_QUESTION_START = re.compile(r"^(can|could|what|how|when|where|why|is|are|does|will|would)\b")


def classify_answer(text: str) -> ConfirmationAnswer:
    """Read a dispatcher's reply, cautiously. Booking needs a clear yes, so anything mixed or
    unsure isn't one, and the worst outcome of a wrong guess is that the agent asks again."""
    spoken = text.lower().replace("’", "'").strip()
    if _NO.search(_NOT_NEGATIVE.sub(" ", spoken)):
        return ConfirmationAnswer.NO
    if "?" in spoken or _QUESTION_START.match(spoken):
        return ConfirmationAnswer.UNCLEAR
    if _YES.search(spoken):
        return ConfirmationAnswer.YES
    if len(spoken.split()) <= _SHORT_REPLY_WORDS and _SHORT_YES.search(spoken):
        return ConfirmationAnswer.YES
    return ConfirmationAnswer.UNCLEAR
