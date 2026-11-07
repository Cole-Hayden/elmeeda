from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.issue import Issue, ProblemType
from issue_tracker.domain.location import Location
from issue_tracker.infrastructure.models import IssueModel


def issue_to_model(issue: Issue) -> IssueModel:
    return IssueModel(
        issue_id=issue.issue_id,
        truck_id=issue.truck_id,
        problem=issue.problem.value if issue.problem else None,
        location_description=issue.location.description if issue.location else None,
        latitude=issue.location.latitude if issue.location else None,
        longitude=issue.location.longitude if issue.location else None,
        drivable=issue.drivable,
        needed_by=issue.needed_by,
        max_distance_miles=issue.max_distance_miles,
        max_budget=issue.max_budget,
    )


def issue_from_model(model: IssueModel) -> Issue:
    location = None
    if (
        model.location_description is not None
        and model.latitude is not None
        and model.longitude is not None
    ):
        location = Location(model.location_description, model.latitude, model.longitude)
    return Issue(
        issue_id=model.issue_id,
        truck_id=model.truck_id,
        problem=ProblemType(model.problem) if model.problem else None,
        location=location,
        drivable=model.drivable,
        needed_by=model.needed_by,
        max_distance_miles=model.max_distance_miles,
        max_budget=model.max_budget,
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

    async def save(self, issue: Issue) -> None:
        try:
            async with self._session_factory.begin() as session:
                await session.merge(issue_to_model(issue))
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc

    async def get(self, issue_id: UUID) -> Issue | None:
        try:
            async with self._session_factory() as session:
                model = await session.get(IssueModel, issue_id)
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
        return issue_from_model(model) if model else None
