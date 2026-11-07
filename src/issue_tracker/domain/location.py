from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.8


@dataclass(frozen=True, slots=True)
class Location:
    description: str
    latitude: float
    longitude: float

    def miles_to(self, other: Location) -> float:
        """Straight-line (haversine) distance; road distance will be somewhat longer."""
        delta_latitude = radians(other.latitude - self.latitude)
        delta_longitude = radians(other.longitude - self.longitude)
        a = (
            sin(delta_latitude / 2) ** 2
            + cos(radians(self.latitude))
            * cos(radians(other.latitude))
            * sin(delta_longitude / 2) ** 2
        )
        return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))
