"""FastAPI dependencies and HTTP errors shared by the voice routes and the dev-only issue routes."""

from fastapi import HTTPException, Request, status

from issue_tracker.application.issue_service import IssueService
from issue_tracker.application.triage_service import TriageService
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.issue_repository import SqlAlchemyIssueRepository
from issue_tracker.infrastructure.job_repository import SqlAlchemyJobRepository
from issue_tracker.infrastructure.shop_repository import SqlAlchemyMaintenanceShopRepository
from issue_tracker.infrastructure.truck_repository import SqlAlchemyTruckRepository


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
