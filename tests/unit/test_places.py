import pytest

from issue_tracker.domain.places import find_place
from issue_tracker.infrastructure.mock_data import KNOWN_PLACES


@pytest.mark.parametrize(
    "spoken", ["I-55 near Joliet", "on the interstate by joliet.", "JOLIET, Illinois"]
)
def test_finds_joliet_however_it_is_said(spoken: str) -> None:
    place = find_place(spoken, KNOWN_PLACES)

    assert place is not None
    assert place.description == "I-55 near Joliet, IL"
    assert (place.latitude, place.longitude) == (41.4900, -88.1950)


@pytest.mark.parametrize(
    "spoken",
    [
        "somewhere in Nebraska",
        "",
        "Joliets",  # Only whole words count.
        "between Joliet and Wilmington",  # Naming two places isn't a location.
    ],
)
def test_returns_none_unless_exactly_one_place_is_named(spoken: str) -> None:
    assert find_place(spoken, KNOWN_PLACES) is None
