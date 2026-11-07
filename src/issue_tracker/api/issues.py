from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, StringConstraints

from issue_tracker.application.issue_service import (
    IssueDetails,
    IssueService,
    NeededByInPastError,
    UnknownTruckError,
)
from issue_tracker.application.ports import IssueBookedError, IssueNotFoundError
from issue_tracker.application.triage_service import TriageResult, TriageService, TriageStatus
from issue_tracker.domain.issue import Contact, FaultCode, Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.domain.vendor_matching import ExclusionReason
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.job_repository import SqlAlchemyJobRepository
from issue_tracker.infrastructure.shop_repository import SqlAlchemyMaintenanceShopRepository
from issue_tracker.infrastructure.truck_repository import SqlAlchemyTruckRepository

router = APIRouter(prefix="/issues", tags=["issues"])

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
    )


def get_issue_service(request: Request) -> IssueService:
    session_factory = request.app.state.session_factory
    return IssueService(
        SqlAlchemyIssueRepository(session_factory),
        SqlAlchemyTruckRepository(session_factory),
        request.app.state.today,
    )


def get_triage_service(request: Request) -> TriageService:
    session_factory = request.app.state.session_factory
    return TriageService(
        SqlAlchemyTruckRepository(session_factory),
        SqlAlchemyJobRepository(session_factory),
        SqlAlchemyMaintenanceShopRepository(session_factory),
        SqlAlchemyBookingRepository(session_factory),
    )


def invalid_details(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def issue_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No issue has that ID.")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_issue(
    response: Response,
    issues: Annotated[IssueService, Depends(get_issue_service)],
    triage: Annotated[TriageService, Depends(get_triage_service)],
    payload: IssueRequest | None = None,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> TriageResponse:
    details = payload.to_details() if payload else None
    try:
        if idempotency_key is None:
            issue = await issues.create_issue(details)
        else:
            issue, created = await issues.create_or_get_issue(details, idempotency_key)
            if not created:
                response.status_code = status.HTTP_200_OK
    except UnknownTruckError as exc:
        raise invalid_details("No truck has that unit number.") from exc
    except NeededByInPastError as exc:
        raise invalid_details("neededBy can't be in the past.") from exc
    return triage_response(await triage.triage(issue))


@router.get("/{issue_id}")
async def read_issue(
    issue_id: UUID,
    issues: Annotated[IssueService, Depends(get_issue_service)],
    triage: Annotated[TriageService, Depends(get_triage_service)],
) -> TriageResponse:
    try:
        issue = await issues.get_issue(issue_id)
    except IssueNotFoundError as exc:
        raise issue_not_found() from exc
    return triage_response(await triage.triage(issue))


@router.patch("/{issue_id}")
async def update_issue(
    issue_id: UUID,
    payload: IssueRequest,
    issues: Annotated[IssueService, Depends(get_issue_service)],
    triage: Annotated[TriageService, Depends(get_triage_service)],
) -> TriageResponse:
    try:
        issue = await issues.update_issue(issue_id, payload.to_details())
    except IssueNotFoundError as exc:
        raise issue_not_found() from exc
    except IssueBookedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This issue is already booked."
        ) from exc
    except UnknownTruckError as exc:
        raise invalid_details("No truck has that unit number.") from exc
    except NeededByInPastError as exc:
        raise invalid_details("neededBy can't be in the past.") from exc
    return triage_response(await triage.triage(issue))
