"""Fictional data for the Truck 214 breakdown scenario. No real shops, customers, or bookings.

Against the scenario's limits (today, within 30 miles, under $1,500), the shops are built so
the agent has a real tradeoff to explain:

- Rockdale Junction is closest but starts latest and has little room left in the budget.
- Woodridge Fleet is cheapest and starts sooner but is the farthest away.
- Millrace Diesel starts first but is over budget, so it should not be offered as a fit.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.domain.maintenance_shop import MaintenanceShop
from issue_tracker.domain.truck import Truck

CENTRAL = ZoneInfo("America/Chicago")
SCENARIO_DAY = date(2026, 11, 7)

TRUCK_214 = Truck(
    truck_id=UUID("21400000-0000-4000-8000-000000000214"),
    unit_number="214",
    make="Freightliner",
    model="Cascadia",
    year=2021,
)

TRUCKS = (
    TRUCK_214,
    Truck(
        truck_id=UUID("11800000-0000-4000-8000-000000000118"),
        unit_number="118",
        make="Kenworth",
        model="T680",
        year=2019,
    ),
    Truck(
        truck_id=UUID("30200000-0000-4000-8000-000000000302"),
        unit_number="302",
        make="Volvo",
        model="VNL 760",
        year=2023,
    ),
)

ROCKDALE_JUNCTION = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000001"),
    name="Rockdale Junction Truck Care",
    location=Location("Rockdale, IL", 41.5067, -88.1150),
    open_bays=1,
    earliest_start=datetime(2026, 11, 7, 15, 30, tzinfo=CENTRAL),
    estimates={
        ProblemType.COOLANT_LEAK: Decimal("1380.00"),
        ProblemType.TIRE_BLOWOUT: Decimal("640.00"),
    },
)

WOODRIDGE_FLEET = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000002"),
    name="Woodridge Fleet Service",
    location=Location("Woodridge, IL", 41.7470, -88.0500),
    open_bays=2,
    earliest_start=datetime(2026, 11, 7, 13, 0, tzinfo=CENTRAL),
    estimates={
        ProblemType.COOLANT_LEAK: Decimal("1120.00"),
        ProblemType.TIRE_BLOWOUT: Decimal("580.00"),
        ProblemType.BRAKE_FAILURE: Decimal("1450.00"),
    },
)

MILLRACE_DIESEL = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000003"),
    name="Millrace Diesel Works",
    location=Location("Wilmington, IL", 41.3078, -88.1467),
    open_bays=3,
    earliest_start=datetime(2026, 11, 7, 11, 30, tzinfo=CENTRAL),
    estimates={
        ProblemType.COOLANT_LEAK: Decimal("1640.00"),
        ProblemType.BRAKE_FAILURE: Decimal("1725.00"),
    },
)

SHOPS = (ROCKDALE_JUNCTION, WOODRIDGE_FLEET, MILLRACE_DIESEL)

# The dispatcher's opening request. It doesn't say whether the truck can be driven,
# so that is what the agent should ask.
SCENARIO_ISSUE = Issue(
    issue_id=UUID("b0000000-0000-4000-8000-000000000214"),
    truck_id=TRUCK_214.truck_id,
    problem=ProblemType.COOLANT_LEAK,
    location=Location("I-55 near Joliet, IL", 41.4900, -88.1950),
    needed_by=SCENARIO_DAY,
    max_distance_miles=30,
    max_budget=Decimal("1500.00"),
)
