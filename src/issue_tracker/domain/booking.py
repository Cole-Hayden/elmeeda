import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

# Leaves out characters that are easily confused when read aloud or heard (0/O, 1/I/L).
BOOKING_ID_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
BOOKING_ID_LENGTH = 6


@dataclass(frozen=True, slots=True)
class Booking:
    """A confirmed repair. The ID is short so the agent can read it back over voice."""

    booking_id: str
    issue_id: UUID
    shop_id: UUID
    estimate: Decimal
    start_time: datetime

    @classmethod
    def create(
        cls, issue_id: UUID, shop_id: UUID, estimate: Decimal, start_time: datetime
    ) -> Self:
        code = "".join(secrets.choice(BOOKING_ID_ALPHABET) for _ in range(BOOKING_ID_LENGTH))
        return cls(
            booking_id=f"BK-{code}",
            issue_id=issue_id,
            shop_id=shop_id,
            estimate=estimate,
            start_time=start_time,
        )
