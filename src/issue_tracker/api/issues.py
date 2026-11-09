"""Dev-only routes for creating and reading an issue without a voice call.

They're mounted only when `enable_dev_api` is on, and hidden from the API docs. Dispatchers use
the voice agent, so there's deliberately no route here to change, list, or book an issue: changing
one goes through the voice tools, which apply the limit-change rule.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status

from issue_tracker.api.dependencies import (
    get_issue_service,
    get_triage_service,
    invalid_details,
    issue_not_found,
)
from issue_tracker.api.schemas import IssueRequest, TriageResponse, triage_response
from issue_tracker.application.issue_service import (
    IssueService,
    NeededByInPastError,
    UnknownTruckError,
)
from issue_tracker.application.ports import IssueNotFoundError
from issue_tracker.application.triage_service import TriageService

router = APIRouter(prefix="/issues", tags=["dev"], include_in_schema=False)


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
