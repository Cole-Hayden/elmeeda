from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from issue_tracker.domain.read_back import read_back_matches, read_back_text

CENTRAL = ZoneInfo("America/Chicago")
SHOP = "Rockdale Junction Truck Care"
ESTIMATE = Decimal("1380.00")
START = datetime(2026, 11, 7, 17, 15, tzinfo=CENTRAL)


def test_the_suggested_words_state_every_detail() -> None:
    assert read_back_text(SHOP, ESTIMATE, START) == (
        "Rockdale Junction Truck Care, $1,380.00, starting Saturday at 5:15 PM"
    )


@pytest.mark.parametrize(
    ("estimate", "start"),
    [
        (ESTIMATE, START),
        (Decimal("1120.50"), datetime(2026, 11, 7, 9, 0, tzinfo=CENTRAL)),
        (Decimal("99.00"), datetime(2026, 11, 7, 0, 5, tzinfo=CENTRAL)),
        (Decimal("2000.00"), datetime(2026, 11, 7, 12, 0, tzinfo=CENTRAL)),
    ],
)
def test_the_suggested_words_always_match(estimate: Decimal, start: datetime) -> None:
    assert read_back_matches(read_back_text(SHOP, estimate, start), SHOP, estimate, start)


@pytest.mark.parametrize(
    "spoken",
    [
        "Rockdale Junction Truck Care, $1,380, starting at 5:15 PM. Should I book it?",
        "That's Rockdale for $1,380.00 at 5:15pm, okay?",
        "Rockdale, 1380 dollars, 5:15 p.m.",
        "Rockdale, thirteen eighty, at five fifteen.",
        "Rockdale, one thousand three hundred eighty dollars, at five fifteen PM.",
        "Rockdale, one thousand three hundred and eighty dollars, five-fifteen in the evening.",
        "Rockdale, thirteen hundred eighty dollars, at 17:15.",
    ],
)
def test_ways_of_saying_the_same_details_match(spoken: str) -> None:
    assert read_back_matches(spoken, SHOP, ESTIMATE, START)


@pytest.mark.parametrize(
    "spoken",
    [
        "Should I go ahead and book it?",
        "Woodridge, $1,380, at 5:15 PM.",
        "Rockdale, at 5:15 PM.",
        "Rockdale, $1,300, at 5:15 PM.",
        "Rockdale, $1,380.",
        "Rockdale, $1,380, at 5:15 AM.",
        "Rockdale, $1,380, at 6:15 PM.",
        "Rockdale, $1,380, at 15:15.",
        "Rockdale, $1,380, at 5 PM.",
    ],
)
def test_missing_or_different_details_do_not_match(spoken: str) -> None:
    assert not read_back_matches(spoken, SHOP, ESTIMATE, START)


@pytest.mark.parametrize(
    "spoken",
    ["Rockdale, $1,380, at 5 PM.", "Rockdale, $1,380, at five o'clock.", "Rockdale, $1,380, 5:00."],
)
def test_a_time_on_the_hour_can_leave_out_the_minutes(spoken: str) -> None:
    assert read_back_matches(spoken, SHOP, ESTIMATE, START.replace(minute=0))


def test_a_morning_start_does_not_match_the_same_time_in_the_afternoon() -> None:
    morning = START.replace(hour=5)

    assert read_back_matches("Rockdale, $1,380, at 5:15 AM.", SHOP, ESTIMATE, morning)
    assert read_back_matches("Rockdale, $1,380, at 5:15.", SHOP, ESTIMATE, morning)
    assert not read_back_matches("Rockdale, $1,380, at 5:15 PM.", SHOP, ESTIMATE, morning)


def test_a_time_on_the_hour_must_not_state_the_wrong_half_of_the_day() -> None:
    assert not read_back_matches(
        "Rockdale, $1,380, at 5:00 AM.", SHOP, ESTIMATE, START.replace(minute=0)
    )
    assert not read_back_matches(
        "Rockdale, $1,380, at 5 AM.", SHOP, ESTIMATE, START.replace(minute=0)
    )


def test_a_bare_number_is_not_a_time() -> None:
    assert not read_back_matches(
        "Rockdale, $1,380, 5 bays.", SHOP, ESTIMATE, START.replace(minute=0)
    )


def test_noon_counts_as_twelve_pm_only() -> None:
    noon = START.replace(hour=12, minute=0)

    assert read_back_matches("Rockdale, $1,380, at noon.", SHOP, ESTIMATE, noon)
    assert not read_back_matches("Rockdale, $1,380, at noon.", SHOP, ESTIMATE, noon.replace(hour=0))


def test_cents_must_match() -> None:
    estimate = Decimal("1380.50")

    assert read_back_matches("Rockdale, $1,380.50, 5:15 PM.", SHOP, estimate, START)
    assert read_back_matches("Rockdale, 1380 dollars and 50 cents, 5:15 PM.", SHOP, estimate, START)
    assert not read_back_matches("Rockdale, $1,380, 5:15 PM.", SHOP, estimate, START)
