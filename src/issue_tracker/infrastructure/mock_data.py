"""Fictional data for the Truck 214 breakdown scenario. No real shops, customers, or bookings.

Against the scenario's limits (today, within 30 miles, under $1,500), the shops are built so
the agent has a real tradeoff to explain, whether or not the truck needs a tow:

- Rockdale Junction is closest but starts latest and has little room left in the budget.
- Woodridge Fleet is cheapest and starts sooner but is the farthest away.
- Millrace Diesel starts first but is over budget, so it should not be offered as a fit.

Labor hours, parts, and rates are chosen so each calculated estimate is a round number.
"""

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from issue_tracker.application.clock import central_today
from issue_tracker.domain.issue import Contact, Issue, ProblemType
from issue_tracker.domain.job import Job, JobPart
from issue_tracker.domain.location import Location
from issue_tracker.domain.maintenance_shop import MaintenanceShop, TowService, VendorCapability
from issue_tracker.domain.truck import Truck

CENTRAL = ZoneInfo("America/Chicago")
# Today, so the scenario still works on whichever day the data is loaded.
SCENARIO_DAY = central_today()

TRUCK_214 = Truck(
    truck_id=UUID("21400000-0000-4000-8000-000000000214"),
    unit_number="214",
    make="Freightliner",
    model="Cascadia",
    year=2021,
    vin="1TEST000000000214",
    engine="DD15",
)

TRUCK_118 = Truck(
    truck_id=UUID("11800000-0000-4000-8000-000000000118"),
    unit_number="118",
    make="Kenworth",
    model="T680",
    year=2019,
    vin="1TEST000000000118",
    engine="MX-13",
)

TRUCKS = (
    TRUCK_214,
    TRUCK_118,
    Truck(
        truck_id=UUID("30200000-0000-4000-8000-000000000302"),
        unit_number="302",
        make="Volvo",
        model="VNL 760",
        year=2023,
        vin="1TEST000000000302",
        engine="D13",
    ),
)

COOLANT_LEAK_JOB = Job(
    job_code="COOLANT_LEAK_GENERIC",
    problem=ProblemType.COOLANT_LEAK,
    name="Coolant leak repair",
    labor_hours=Decimal("4.0"),
    parts=(
        JobPart("MOCK-COOL-GAL", "Coolant, per gallon", 4, Decimal("15.00")),
        JobPart("MOCK-HOSE-KIT", "Radiator hose kit", 1, Decimal("340.00")),
    ),
)

TIRE_BLOWOUT_JOB = Job(
    job_code="TIRE_BLOWOUT_GENERIC",
    problem=ProblemType.TIRE_BLOWOUT,
    name="Tire replacement",
    labor_hours=Decimal("1.0"),
    parts=(JobPart("MOCK-TIRE-STEER", "Replacement tire", 1, Decimal("400.00")),),
)

BRAKE_FAILURE_JOB = Job(
    job_code="BRAKE_FAILURE_GENERIC",
    problem=ProblemType.BRAKE_FAILURE,
    name="Brake repair",
    labor_hours=Decimal("5.0"),
    parts=(
        JobPart("MOCK-BRAKE-CHAMBER", "Brake chamber", 2, Decimal("125.00")),
        JobPart("MOCK-BRAKE-SHOES", "Brake shoe kit", 1, Decimal("300.00")),
    ),
)

DIAGNOSTIC_JOB = Job(
    job_code="DIAGNOSTIC_GENERIC",
    problem=ProblemType.UNKNOWN,
    name="Diagnosis",
    labor_hours=Decimal("2.0"),
    requires_diagnosis=True,
)

JOBS = (COOLANT_LEAK_JOB, TIRE_BLOWOUT_JOB, BRAKE_FAILURE_JOB, DIAGNOSTIC_JOB)

TOW = TowService(base_fee=Decimal("60.00"), per_mile=Decimal("4.00"))

ROCKDALE_JUNCTION = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000001"),
    name="Rockdale Junction Truck Care",
    location=Location("Rockdale, IL", 41.5067, -88.1150),
    open_bays=1,
    earliest_start=datetime.combine(SCENARIO_DAY, time(15, 30), CENTRAL),
    capabilities={
        COOLANT_LEAK_JOB.job_code: VendorCapability(Decimal("245.00")),
        TIRE_BLOWOUT_JOB.job_code: VendorCapability(Decimal("240.00")),
        DIAGNOSTIC_JOB.job_code: VendorCapability(Decimal("245.00")),
    },
    tow=TOW,
)

WOODRIDGE_FLEET = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000002"),
    name="Woodridge Fleet Service",
    location=Location("Woodridge, IL", 41.7470, -88.0500),
    open_bays=2,
    earliest_start=datetime.combine(SCENARIO_DAY, time(13, 0), CENTRAL),
    capabilities={
        COOLANT_LEAK_JOB.job_code: VendorCapability(Decimal("180.00")),
        TIRE_BLOWOUT_JOB.job_code: VendorCapability(Decimal("180.00")),
        BRAKE_FAILURE_JOB.job_code: VendorCapability(Decimal("180.00")),
        DIAGNOSTIC_JOB.job_code: VendorCapability(Decimal("180.00")),
    },
    tow=TowService(base_fee=Decimal("60.00"), per_mile=Decimal("4.00"), hazmat=True),
)

MILLRACE_MAKES = frozenset({"Freightliner", "Volvo"})

MILLRACE_DIESEL = MaintenanceShop(
    shop_id=UUID("a0000000-0000-4000-8000-000000000003"),
    name="Millrace Diesel Works",
    location=Location("Wilmington, IL", 41.3078, -88.1467),
    open_bays=3,
    earliest_start=datetime.combine(SCENARIO_DAY, time(11, 30), CENTRAL),
    capabilities={
        COOLANT_LEAK_JOB.job_code: VendorCapability(Decimal("310.00"), MILLRACE_MAKES),
        BRAKE_FAILURE_JOB.job_code: VendorCapability(Decimal("235.00"), MILLRACE_MAKES),
        DIAGNOSTIC_JOB.job_code: VendorCapability(Decimal("310.00"), MILLRACE_MAKES),
    },
    tow=TOW,
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
    symptoms="Coolant is leaking under the engine and the temperature is climbing.",
    contact=Contact("Fleet Dispatch", "555-0100"),
)
