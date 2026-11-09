"""Request and response models shared by the voice routes and the dev-only issue routes."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from issue_tracker.application.issue_service import IssueDetails
from issue_tracker.application.shop_checks import ShopFailure
from issue_tracker.application.triage_service import TriageResult, TriageStatus
from issue_tracker.domain.issue import Contact, FaultCode, Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.domain.vendor_matching import ExclusionReason

MISSING_DETAIL_FIELDS = {
    "truck_id": "truckUnitNumber",
    "problem": "problem",
    "location": "location",
    "drivable": "drivable",
    "needed_by": "neededBy",
    "max_distance_miles": "maxDistanceMiles",
    "max_budget": "maxBudget",
    "symptoms": "symptoms",
    "contact": "contact",
    "loaded": "loaded",
    "hazmat": "hazmat",
}


class LocationRequest(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ContactRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class FaultCodeRequest(BaseModel):
    spn: int = Field(ge=0, le=524287)
    fmi: int = Field(ge=0, le=31)


class IssueRequest(BaseModel):
    """Every field is optional because a call starts with whatever the dispatcher says first."""

    truck_unit_number: str | None = Field(
        default=None, validation_alias="truckUnitNumber", min_length=1, max_length=32
    )
    problem: ProblemType | None = None
    location: LocationRequest | None = None
    drivable: bool | None = None
    needed_by: date | None = Field(default=None, validation_alias="neededBy")
    max_distance_miles: float | None = Field(
        default=None, validation_alias="maxDistanceMiles", gt=0, allow_inf_nan=False
    )
    max_budget: Decimal | None = Field(
        default=None, validation_alias="maxBudget", gt=0, max_digits=10, decimal_places=2
    )
    symptoms: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
        | None
    ) = None
    contact: ContactRequest | None = None
    loaded: bool | None = None
    hazmat: bool | None = None
    odometer_miles: int | None = Field(default=None, validation_alias="odometerMiles", ge=0)
    fault_codes: list[FaultCodeRequest] | None = Field(default=None, validation_alias="faultCodes")

    def to_details(self) -> IssueDetails:
        location = None
        if self.location is not None:
            location = Location(
                self.location.description, self.location.latitude, self.location.longitude
            )
        return IssueDetails(
            truck_unit_number=self.truck_unit_number,
            problem=self.problem,
            location=location,
            drivable=self.drivable,
            needed_by=self.needed_by,
            max_distance_miles=self.max_distance_miles,
            max_budget=self.max_budget,
            symptoms=self.symptoms,
            contact=Contact(self.contact.name, self.contact.phone) if self.contact else None,
            loaded=self.loaded,
            hazmat=self.hazmat,
            odometer_miles=self.odometer_miles,
            fault_codes=(
                tuple(FaultCode(code.spn, code.fmi) for code in self.fault_codes)
                if self.fault_codes is not None
                else None
            ),
        )


class TruckResponse(BaseModel):
    unit_number: str = Field(serialization_alias="unitNumber")
    make: str
    model: str
    year: int
    vin: str | None
    engine: str | None


class LocationResponse(BaseModel):
    description: str
    latitude: float
    longitude: float


class ContactResponse(BaseModel):
    name: str
    phone: str


class FaultCodeResponse(BaseModel):
    spn: int
    fmi: int


class DetailsResponse(BaseModel):
    problem: ProblemType | None
    location: LocationResponse | None
    drivable: bool | None
    needed_by: date | None = Field(serialization_alias="neededBy")
    max_distance_miles: float | None = Field(serialization_alias="maxDistanceMiles")
    max_budget: Decimal | None = Field(serialization_alias="maxBudget")
    symptoms: str | None
    contact: ContactResponse | None
    loaded: bool | None
    hazmat: bool | None
    odometer_miles: int | None = Field(serialization_alias="odometerMiles")
    fault_codes: list[FaultCodeResponse] = Field(serialization_alias="faultCodes")


class PartResponse(BaseModel):
    part_number: str = Field(serialization_alias="partNumber")
    description: str
    quantity: int
    unit_price: Decimal = Field(serialization_alias="unitPrice")


class JobResponse(BaseModel):
    job_code: str = Field(serialization_alias="jobCode")
    name: str
    labor_hours: Decimal = Field(serialization_alias="laborHours")
    requires_diagnosis: bool = Field(serialization_alias="requiresDiagnosis")
    vmrs_code: str | None = Field(serialization_alias="vmrsCode")
    parts: list[PartResponse]


class BreakdownResponse(BaseModel):
    labor: Decimal
    parts: Decimal
    tow: Decimal


class OptionResponse(BaseModel):
    shop_id: UUID = Field(serialization_alias="shopId")
    name: str
    distance_miles: float = Field(serialization_alias="distanceMiles")
    open_bays: int = Field(serialization_alias="openBays")
    earliest_start: datetime = Field(serialization_alias="earliestStart")
    estimate: Decimal
    breakdown: BreakdownResponse


class ExcludedResponse(BaseModel):
    shop_id: UUID = Field(serialization_alias="shopId")
    name: str
    reason: ExclusionReason


class UnavailableResponse(BaseModel):
    shop_id: UUID = Field(serialization_alias="shopId")
    name: str
    reason: ShopFailure


class TriageResponse(BaseModel):
    issue_id: UUID = Field(serialization_alias="issueId")
    status: TriageStatus
    missing_details: list[str] = Field(serialization_alias="missingDetails")
    tow_required: bool = Field(serialization_alias="towRequired")
    truck: TruckResponse | None
    details: DetailsResponse
    job: JobResponse | None
    options: list[OptionResponse]
    excluded: list[ExcludedResponse]
    unavailable: list[UnavailableResponse]


def details_response(issue: Issue) -> DetailsResponse:
    location = None
    if issue.location is not None:
        location = LocationResponse(
            description=issue.location.description,
            latitude=issue.location.latitude,
            longitude=issue.location.longitude,
        )
    contact = None
    if issue.contact is not None:
        contact = ContactResponse(name=issue.contact.name, phone=issue.contact.phone)
    return DetailsResponse(
        problem=issue.problem,
        location=location,
        drivable=issue.drivable,
        needed_by=issue.needed_by,
        max_distance_miles=issue.max_distance_miles,
        max_budget=issue.max_budget,
        symptoms=issue.symptoms,
        contact=contact,
        loaded=issue.loaded,
        hazmat=issue.hazmat,
        odometer_miles=issue.odometer_miles,
        fault_codes=[FaultCodeResponse(spn=code.spn, fmi=code.fmi) for code in issue.fault_codes],
    )


def triage_response(result: TriageResult) -> TriageResponse:
    issue, truck, job = result.issue, result.truck, result.job
    return TriageResponse(
        issue_id=issue.issue_id,
        status=result.status,
        missing_details=[MISSING_DETAIL_FIELDS[name] for name in issue.missing_details()],
        tow_required=issue.tow_required,
        truck=(
            TruckResponse(
                unit_number=truck.unit_number,
                make=truck.make,
                model=truck.model,
                year=truck.year,
                vin=truck.vin,
                engine=truck.engine,
            )
            if truck
            else None
        ),
        details=details_response(issue),
        job=(
            JobResponse(
                job_code=job.job_code,
                name=job.name,
                labor_hours=job.labor_hours,
                requires_diagnosis=job.requires_diagnosis,
                vmrs_code=job.vmrs_code,
                parts=[
                    PartResponse(
                        part_number=part.part_number,
                        description=part.description,
                        quantity=part.quantity,
                        unit_price=part.unit_price,
                    )
                    for part in job.parts
                ],
            )
            if job
            else None
        ),
        options=[
            OptionResponse(
                shop_id=option.shop.shop_id,
                name=option.shop.name,
                distance_miles=round(option.distance_miles, 1),
                open_bays=option.shop.open_bays,
                earliest_start=option.shop.earliest_start,
                estimate=option.quote.estimate,
                breakdown=BreakdownResponse(
                    labor=option.quote.labor, parts=option.quote.parts, tow=option.quote.tow
                ),
            )
            for option in result.options
        ],
        excluded=[
            ExcludedResponse(
                shop_id=vendor.shop.shop_id, name=vendor.shop.name, reason=vendor.reason
            )
            for vendor in result.excluded
        ],
        unavailable=[
            UnavailableResponse(
                shop_id=vendor.shop.shop_id, name=vendor.shop.name, reason=vendor.failure
            )
            for vendor in result.unavailable
        ],
    )
