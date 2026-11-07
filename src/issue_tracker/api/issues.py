from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from issue_tracker.application.issue_service import IssueDetails, IssueService, UnknownTruckError
from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.truck_repository import SqlAlchemyTruckRepository

router = APIRouter(prefix="/issues", tags=["issues"])


class LocationRequest(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


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
        )


class IssueResponse(BaseModel):
    issue_id: UUID = Field(serialization_alias="issueId")


def get_issue_service(request: Request) -> IssueService:
    session_factory = request.app.state.session_factory
    return IssueService(
        SqlAlchemyIssueRepository(session_factory),
        SqlAlchemyTruckRepository(session_factory),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_issue(
    service: Annotated[IssueService, Depends(get_issue_service)],
    payload: IssueRequest | None = None,
) -> IssueResponse:
    details = payload.to_details() if payload else None
    try:
        issue = await service.create_issue(details)
    except UnknownTruckError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No truck has that unit number.",
        ) from exc
    return IssueResponse(issue_id=issue.issue_id)
