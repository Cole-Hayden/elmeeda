import logging
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from issue_tracker.api.dependencies import get_issue_service, issue_not_found
from issue_tracker.api.schemas import IssueRequest, triage_response
from issue_tracker.application.booking_service import BookingService
from issue_tracker.application.issue_service import (
    IssueService,
    NeededByInPastError,
    UnknownTruckError,
)
from issue_tracker.application.ports import (
    BookingRejectedError,
    IssueBookedError,
    IssueNotFoundError,
)
from issue_tracker.application.shop_checks import ShopChecker, ShopFault, ShopUnavailableError
from issue_tracker.application.triage_service import TriageResult, TriageService
from issue_tracker.application.voice_agent import (
    RealtimeCallError,
    RealtimeGateway,
    agent_config,
)
from issue_tracker.application.voice_tools import (
    ConfirmationRequiredError,
    ConfirmedBooking,
    ReadBackRequiredError,
    ShopNotAvailableError,
    VoiceTools,
)
from issue_tracker.domain.confirmation import ConfirmationAnswer
from issue_tracker.domain.read_back import read_back_text
from issue_tracker.infrastructure.booking_repository import SqlAlchemyBookingRepository
from issue_tracker.infrastructure.confirmation_repository import SqlAlchemyConfirmationRepository
from issue_tracker.infrastructure.job_repository import SqlAlchemyJobRepository
from issue_tracker.infrastructure.limit_change_repository import SqlAlchemyLimitChangeRepository
from issue_tracker.infrastructure.mock_data import KNOWN_PLACES
from issue_tracker.infrastructure.shop_repository import SqlAlchemyMaintenanceShopRepository
from issue_tracker.infrastructure.truck_repository import SqlAlchemyTruckRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

ToolResult = dict[str, Any]


class ToolName(StrEnum):
    UPDATE_ISSUE = "update_issue"
    SEARCH_SHOPS = "search_shops"
    PREPARE_BOOKING = "prepare_booking"
    BOOK_REPAIR = "book_repair"


class VoiceCallResponse(BaseModel):
    issue_id: UUID = Field(serialization_alias="issueId")
    sdp: str


class ShopArguments(BaseModel):
    shop_id: UUID = Field(validation_alias="shopId")


class AnswerRequest(BaseModel):
    confirmation_id: UUID = Field(validation_alias="confirmationId")
    text: str = Field(max_length=2000)


class AnswerResponse(BaseModel):
    answer: ConfirmationAnswer
    confirmed: bool


class ReadBackResponse(BaseModel):
    matched: bool


class ShopControlResponse(BaseModel):
    shop_id: UUID = Field(serialization_alias="shopId")
    name: str
    open_bays: int = Field(serialization_alias="openBays")
    fault: ShopFault


class FaultRequest(BaseModel):
    fault: ShopFault


class BookedRepairResponse(BaseModel):
    booking_id: str = Field(serialization_alias="bookingId")
    truck_unit_number: str = Field(serialization_alias="truckUnitNumber")
    problem: str | None
    location: str | None
    shop_name: str = Field(serialization_alias="shopName")
    estimate: Decimal
    start_time: datetime = Field(serialization_alias="startTime")


def get_realtime_gateway(request: Request) -> RealtimeGateway:
    gateway: RealtimeGateway | None = request.app.state.realtime_gateway
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice isn't configured on this server.",
        )
    return gateway


def get_shop_checker(request: Request) -> ShopChecker:
    checker: ShopChecker = request.app.state.shop_checker
    return checker


def get_voice_tools(
    request: Request,
    issues: Annotated[IssueService, Depends(get_issue_service)],
    checker: Annotated[ShopChecker, Depends(get_shop_checker)],
) -> VoiceTools:
    session_factory = request.app.state.session_factory
    bookings = SqlAlchemyBookingRepository(session_factory)
    shops = SqlAlchemyMaintenanceShopRepository(session_factory)
    return VoiceTools(
        issues,
        TriageService(
            SqlAlchemyTruckRepository(session_factory),
            SqlAlchemyJobRepository(session_factory),
            shops,
            bookings,
            checker,
        ),
        BookingService(bookings),
        SqlAlchemyConfirmationRepository(session_factory),
        SqlAlchemyLimitChangeRepository(session_factory),
        shops,
        checker,
        KNOWN_PLACES,
    )


@router.post("/calls", status_code=status.HTTP_201_CREATED)
async def create_call(
    request: Request,
    gateway: Annotated[RealtimeGateway, Depends(get_realtime_gateway)],
    issues: Annotated[IssueService, Depends(get_issue_service)],
) -> VoiceCallResponse:
    """Takes the browser's SDP offer as the raw body. The call connects first, so a failed
    connection doesn't leave an empty issue behind."""
    sdp_offer = (await request.body()).decode("utf-8", errors="replace")
    if not sdp_offer.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="An SDP offer is required."
        )
    try:
        sdp_answer = await gateway.create_call(sdp_offer, agent_config(request.app.state.today()))
    except RealtimeCallError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    issue = await issues.create_issue(None)
    return VoiceCallResponse(issue_id=issue.issue_id, sdp=sdp_answer)


def _triage_result(result: TriageResult, exclude: set[str]) -> ToolResult:
    # The issue ID is bound in the URL, so the model never needs to see it.
    return triage_response(result).model_dump(
        mode="json", by_alias=True, exclude={"issue_id", *exclude}
    )


def _booking_result(confirmed: ConfirmedBooking) -> ToolResult:
    booking = confirmed.booking
    result: ToolResult = {
        "bookingId": booking.booking_id,
        "shopId": str(booking.shop_id),
        "shopName": confirmed.shop_name,
        "estimate": str(booking.estimate),
        "startTime": booking.start_time.isoformat(),
    }
    if confirmed.already_booked:
        result["alreadyBooked"] = True
    return result


async def _update_issue(tools: VoiceTools, issue_id: UUID, arguments: ToolResult) -> ToolResult:
    # The model names a place and the server finds its coordinates, so any location it sends
    # is ignored.
    fields = {key: value for key, value in arguments.items() if key not in ("place", "location")}
    place = arguments.get("place")
    details = IssueRequest.model_validate(fields).to_details()
    try:
        update = await tools.update_issue(
            issue_id, details, place if isinstance(place, str) else None
        )
    except UnknownTruckError:
        return {"error": "unknown_truck"}
    except NeededByInPastError:
        return {"error": "needed_by_in_past"}
    except IssueBookedError:
        return {"error": "issue_already_booked"}
    result = _triage_result(
        update.triage, exclude={"options", "excluded", "unavailable", "job"}
    )
    if update.location_unknown:
        result["error"] = "location_unknown"
    if update.limit_change is not None:
        change = update.limit_change.change
        result["confirmationId"] = str(update.limit_change.confirmation_id)
        result["limitChangeNeedsYes"] = {
            key: value
            for key, value in (
                ("maxDistanceMiles", change.max_distance_miles),
                ("neededBy", change.needed_by.isoformat() if change.needed_by else None),
                ("maxBudget", str(change.max_budget) if change.max_budget else None),
            )
            if value is not None
        }
    return result


async def _search_shops(tools: VoiceTools, issue_id: UUID) -> ToolResult:
    search = await tools.search_shops(issue_id)
    result = _triage_result(search.triage, exclude=set())
    if search.existing is not None:
        result["existingBooking"] = _booking_result(search.existing)
    return result


async def _prepare_booking(tools: VoiceTools, issue_id: UUID, arguments: ToolResult) -> ToolResult:
    shop_id = ShopArguments.model_validate(arguments).shop_id
    try:
        option = await tools.prepare_booking(issue_id, shop_id)
    except ShopNotAvailableError as exc:
        return {"error": "shop_not_available", "reason": exc.reason}
    prepared = option.prepared
    return {
        "confirmationId": str(prepared.confirmation_id),
        "shopId": str(prepared.shop_id),
        "shopName": option.shop_name,
        "estimate": str(prepared.estimate),
        "startTime": prepared.start_time.isoformat(),
        "readBack": read_back_text(option.shop_name, prepared.estimate, prepared.start_time),
    }


async def _book_repair(tools: VoiceTools, issue_id: UUID, arguments: ToolResult) -> ToolResult:
    shop_id = ShopArguments.model_validate(arguments).shop_id
    try:
        return _booking_result(await tools.book_repair(issue_id, shop_id))
    except ConfirmationRequiredError:
        return {"error": "confirmation_required"}
    except ReadBackRequiredError:
        return {"error": "read_back_required"}
    except ShopUnavailableError as exc:
        return {"error": exc.failure.value}
    except BookingRejectedError as exc:
        return {"error": exc.reason.value}


@router.post("/calls/{issue_id}/tools/{name}")
async def run_tool(
    issue_id: UUID,
    name: ToolName,
    arguments: Annotated[dict[str, Any], Body()],
    tools: Annotated[VoiceTools, Depends(get_voice_tools)],
) -> ToolResult:
    """Failures the agent should explain are normal results with an `error`, so it can state the
    real reason. Only an unknown issue or a storage failure is an HTTP error."""
    try:
        match name:
            case ToolName.UPDATE_ISSUE:
                return await _update_issue(tools, issue_id, arguments)
            case ToolName.SEARCH_SHOPS:
                return await _search_shops(tools, issue_id)
            case ToolName.PREPARE_BOOKING:
                return await _prepare_booking(tools, issue_id, arguments)
            case ToolName.BOOK_REPAIR:
                return await _book_repair(tools, issue_id, arguments)
    except ValidationError as exc:
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return {"error": "invalid_arguments", "fields": fields}
    except IssueNotFoundError as exc:
        raise issue_not_found() from exc


@router.post("/calls/{issue_id}/read-backs")
async def record_read_back(
    issue_id: UUID,
    payload: AnswerRequest,
    tools: Annotated[VoiceTools, Depends(get_voice_tools)],
) -> ReadBackResponse:
    """The transcript of what the agent finished saying, sent by the browser once its audio has
    played. This isn't a tool, so the model can't claim to have said something it didn't."""
    matched = await tools.record_read_back(issue_id, payload.confirmation_id, payload.text)
    logger.warning("Read-back %r matched=%s", payload.text, matched)
    return ReadBackResponse(matched=matched)


@router.post("/calls/{issue_id}/answers")
async def record_answer(
    issue_id: UUID,
    payload: AnswerRequest,
    tools: Annotated[VoiceTools, Depends(get_voice_tools)],
) -> AnswerResponse:
    """The transcript of what the dispatcher said after a read-back. This isn't a tool, so the
    model has no way to call it or to confirm a booking for itself."""
    result = await tools.record_answer(issue_id, payload.confirmation_id, payload.text)
    # Warning level, because uvicorn doesn't show this logger's info messages.
    logger.warning(
        "Confirmation reply %r read as %s, confirmed=%s",
        payload.text,
        result.answer.value,
        result.confirmed,
    )
    return AnswerResponse(answer=result.answer, confirmed=result.confirmed)


@router.get("/bookings")
async def list_bookings(request: Request) -> list[BookedRepairResponse]:
    repairs = await SqlAlchemyBookingRepository(
        request.app.state.session_factory
    ).list_booked_repairs()
    return [
        BookedRepairResponse(
            booking_id=repair.booking.booking_id,
            truck_unit_number=repair.truck_unit_number,
            problem=repair.problem,
            location=repair.location,
            shop_name=repair.shop_name,
            estimate=repair.booking.estimate,
            start_time=repair.booking.start_time,
        )
        for repair in repairs
    ]


@router.get("/shops")
async def list_shops(
    request: Request, checker: Annotated[ShopChecker, Depends(get_shop_checker)]
) -> list[ShopControlResponse]:
    shops = await SqlAlchemyMaintenanceShopRepository(request.app.state.session_factory).list_all()
    return [
        ShopControlResponse(
            shop_id=shop.shop_id,
            name=shop.name,
            open_bays=shop.open_bays,
            fault=checker.fault_for(shop.shop_id),
        )
        for shop in sorted(shops, key=lambda shop: shop.name)
    ]


@router.put("/shops/{shop_id}/fault")
async def set_shop_fault(
    shop_id: UUID,
    payload: FaultRequest,
    request: Request,
    checker: Annotated[ShopChecker, Depends(get_shop_checker)],
) -> ShopControlResponse:
    shops = await SqlAlchemyMaintenanceShopRepository(request.app.state.session_factory).list_all()
    shop = next((shop for shop in shops if shop.shop_id == shop_id), None)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No shop has that ID.")
    checker.set_fault(shop_id, payload.fault)
    return ShopControlResponse(
        shop_id=shop.shop_id, name=shop.name, open_bays=shop.open_bays, fault=payload.fault
    )
