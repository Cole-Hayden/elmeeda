import pytest

from issue_tracker.domain.confirmation import ConfirmationAnswer, classify_answer


@pytest.mark.parametrize(
    "spoken",
    [
        "Yes",
        "yes.",
        "Yeah, book it.",
        "Yep",
        "OK, yes, book it.",
        "Go ahead.",
        "That's right.",
        "That’s right.",
        "Confirmed.",
        "Sounds good, do it.",
        "Sure.",
        "Okay.",
        "OK, go.",
        "Go for it.",
        "That works.",
        "Perfect.",
        "Absolutely.",
        "Sounds great.",
        "Let's go.",
        "Book that.",
        "Yes, no problem.",
        "No problem, go ahead.",
    ],
)
def test_clear_yes(spoken: str) -> None:
    assert classify_answer(spoken) is ConfirmationAnswer.YES


@pytest.mark.parametrize(
    "spoken",
    [
        "No",
        "No, hold on.",
        "Yes, but not that shop.",
        "Yes... actually, wait.",
        "Don't book it.",
        "Please don’t do it.",
        "Cancel that.",
        "Let's use the other one instead.",
        "I can't confirm that yet.",
        "Book the other one.",
        "Okay, hang on.",
        "Not a problem, but wait.",
    ],
)
def test_no_wins_over_anything_else(spoken: str) -> None:
    assert classify_answer(spoken) is ConfirmationAnswer.NO


@pytest.mark.parametrize(
    "spoken",
    [
        "",
        "Um.",
        "Let's go with Rockdale.",
        "Okay, let me think.",
        "Sure, what's the catch",
        "Right, so what about Woodridge",
        "Thank you.",
        "Is that a yes?",
        "Can you confirm the price",
        "What's the estimate again?",
    ],
)
def test_anything_else_is_unclear(spoken: str) -> None:
    assert classify_answer(spoken) is ConfirmationAnswer.UNCLEAR
