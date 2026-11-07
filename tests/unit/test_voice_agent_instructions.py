"""These check that the prompt covers every failure the tools can report. They can't check what
the model then says, which only a live call shows."""

from datetime import date

import pytest

from issue_tracker.application.ports import BookingRejection
from issue_tracker.application.shop_checks import ShopFailure
from issue_tracker.application.triage_service import TriageStatus
from issue_tracker.application.voice_agent import agent_config

INSTRUCTIONS = agent_config(date(2026, 11, 7)).instructions
# Reported by the relay or a tool, rather than coming from an enum.
OTHER_RESULTS = [
    "tool_failed",
    "confirmation_required",
    "read_back_required",
    "limitChangeNeedsYes",
    "location_unknown",
]


@pytest.mark.parametrize("failure", list(ShopFailure))
def test_every_shop_failure_is_explained(failure: ShopFailure) -> None:
    assert failure.value in INSTRUCTIONS


@pytest.mark.parametrize("status", [TriageStatus.NO_VENDOR, TriageStatus.SHOPS_UNAVAILABLE])
def test_each_way_of_having_no_options_is_explained(status: TriageStatus) -> None:
    assert status.value in INSTRUCTIONS


@pytest.mark.parametrize(
    "rejection", [BookingRejection.NO_OPEN_BAY, BookingRejection.QUOTE_CHANGED]
)
def test_rejections_a_shop_can_cause_are_explained(rejection: BookingRejection) -> None:
    assert rejection.value in INSTRUCTIONS


def test_any_other_booking_error_is_still_covered() -> None:
    assert "any other error, nothing was booked" in INSTRUCTIONS


@pytest.mark.parametrize("result", OTHER_RESULTS)
def test_other_results_are_explained(result: str) -> None:
    assert result in INSTRUCTIONS
