from dataclasses import replace

from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.infrastructure.mock_data import SCENARIO_ISSUE


def test_truck_that_cannot_be_driven_needs_a_tow() -> None:
    assert replace(SCENARIO_ISSUE, drivable=False).tow_required is True


def test_failed_brakes_need_a_tow_even_if_the_driver_says_it_can_drive() -> None:
    issue = replace(SCENARIO_ISSUE, drivable=True, problem=ProblemType.BRAKE_FAILURE)

    assert issue.tow_required is True


def test_drivable_truck_needs_no_tow() -> None:
    assert replace(SCENARIO_ISSUE, drivable=True).tow_required is False


def test_unanswered_drivable_does_not_assume_a_tow() -> None:
    assert SCENARIO_ISSUE.drivable is None
    assert SCENARIO_ISSUE.tow_required is False


def test_tow_details_are_asked_only_when_a_tow_is_needed() -> None:
    assert replace(SCENARIO_ISSUE, drivable=True).missing_details() == ()
    assert replace(SCENARIO_ISSUE, drivable=False).missing_details() == ("loaded", "hazmat")


def test_failed_brakes_ask_for_tow_details_and_still_ask_if_drivable() -> None:
    issue = replace(SCENARIO_ISSUE, problem=ProblemType.BRAKE_FAILURE)

    assert issue.missing_details() == ("drivable", "loaded", "hazmat")


def test_false_answers_to_tow_details_count_as_answered() -> None:
    issue = replace(SCENARIO_ISSUE, drivable=False, loaded=False, hazmat=False)

    assert issue.missing_details() == ()


def test_optional_details_are_never_asked_for() -> None:
    missing = Issue.create().missing_details()

    assert "odometer_miles" not in missing
    assert "fault_codes" not in missing
