from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import (
    IssueBookedError,
    IssueNotFoundError,
    StorageUnavailableError,
)
from issue_tracker.domain.issue import Contact, FaultCode, Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.infrastructure.models import BookingModel, IssueModel


def issue_columns(issue: Issue) -> dict[str, Any]:
    return {
        "issue_id": issue.issue_id,
        "truck_id": issue.truck_id,
        "problem": issue.problem.value if issue.problem else None,
        "location_description": issue.location.description if issue.location else None,
        "latitude": issue.location.latitude if issue.location else None,
        "longitude": issue.location.longitude if issue.location else None,
        "drivable": issue.drivable,
        "needed_by": issue.needed_by,
        "max_distance_miles": issue.max_distance_miles,
        "max_budget": issue.max_budget,
        "symptoms": issue.symptoms,
        "contact_name": issue.contact.name if issue.contact else None,
        "contact_phone": issue.contact.phone if issue.contact else None,
        "loaded": issue.loaded,
        "hazmat": issue.hazmat,
        "odometer_miles": issue.odometer_miles,
        "fault_codes": [{"spn": code.spn, "fmi": code.fmi} for code in issue.fault_codes],
    }


def issue_to_model(issue: Issue) -> IssueModel:
    return IssueModel(**issue_columns(issue))


def issue_from_model(model: IssueModel) -> Issue:
    location = None
    if (
        model.location_description is not None
        and model.latitude is not None
        and model.longitude is not None
    ):
        location = Location(model.location_description, model.latitude, model.longitude)
    contact = None
    if model.contact_name is not None and model.contact_phone is not None:
        contact = Contact(model.contact_name, model.contact_phone)
    return Issue(
        issue_id=model.issue_id,
        truck_id=model.truck_id,
        problem=ProblemType(model.problem) if model.problem else None,
        location=location,
        drivable=model.drivable,
        needed_by=model.needed_by,
        max_distance_miles=model.max_distance_miles,
        max_budget=model.max_budget,
        symptoms=model.symptoms,
        contact=contact,
        loaded=model.loaded,
        hazmat=model.hazmat,
        odometer_miles=model.odometer_miles,
        fault_codes=tuple(FaultCode(code["spn"], code["fmi"]) for code in model.fault_codes),
    )


class SqlAlchemyIssueRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, issue: Issue) -> None:
        try:
            async with self._session_factory.begin() as session:
                session.add(issue_to_model(issue))
        # asyncpg raises OSError subclasses, not SQLAlchemy errors, when it cannot connect.
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def add_with_key(self, issue: Issue, idempotency_key: str) -> Issue:
        statement = (
            insert(IssueModel)
            .values(idempotency_key=idempotency_key, **issue_columns(issue))
            # A concurrent insert with this key blocks here until it commits, so the read
            # below always finds the winning row.
            .on_conflict_do_nothing(index_elements=[IssueModel.idempotency_key])
        )
        try:
            async with self._session_factory.begin() as session:
                await session.execute(statement)
                model = await session.scalar(
                    select(IssueModel).where(IssueModel.idempotency_key == idempotency_key)
                )
                if model is None:
                    raise StorageUnavailableError
                return issue_from_model(model)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get_by_key(self, idempotency_key: str) -> Issue | None:
        try:
            async with self._session_factory() as session:
                model = await session.scalar(
                    select(IssueModel).where(IssueModel.idempotency_key == idempotency_key)
                )
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return issue_from_model(model) if model else None

    async def save(self, issue: Issue) -> None:
        try:
            async with self._session_factory.begin() as session:
                await session.merge(issue_to_model(issue))
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def update_unless_booked(
        self, issue_id: UUID, change: Callable[[Issue], Issue]
    ) -> Issue:
        try:
            async with self._session_factory.begin() as session:
                # Booking takes this same lock first, so an update and a booking can't interleave.
                model = await session.scalar(
                    select(IssueModel).where(IssueModel.issue_id == issue_id).with_for_update()
                )
                if model is None:
                    raise IssueNotFoundError
                booking_id = await session.scalar(
                    select(BookingModel.booking_id).where(BookingModel.issue_id == issue_id)
                )
                if booking_id is not None:
                    raise IssueBookedError
                updated = change(issue_from_model(model))
                for column, value in issue_columns(updated).items():
                    setattr(model, column, value)
                return updated
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get(self, issue_id: UUID) -> Issue | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(IssueModel, issue_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return issue_from_model(model) if model else None
