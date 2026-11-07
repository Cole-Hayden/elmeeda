import re
from collections.abc import Iterable
from dataclasses import dataclass

from issue_tracker.domain.location import Location


@dataclass(frozen=True, slots=True)
class KnownPlace:
    location: Location
    # Lowercase words a dispatcher would say for this place.
    aliases: tuple[str, ...]


def find_place(spoken: str, places: Iterable[KnownPlace]) -> Location | None:
    """Return the one place the words name. Naming none or several returns None, because
    guessing would quote distances and tow costs from the wrong location."""
    words = f" {' '.join(re.findall(r'[a-z0-9-]+', spoken.lower()))} "
    matches = [
        place.location for place in places if any(f" {alias} " in words for alias in place.aliases)
    ]
    return matches[0] if len(matches) == 1 else None
