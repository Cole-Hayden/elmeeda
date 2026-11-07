from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.job import Job, JobPart
from issue_tracker.infrastructure.models import JobModel


def job_from_model(model: JobModel) -> Job:
    return Job(
        job_code=model.job_code,
        problem=ProblemType(model.problem),
        name=model.name,
        labor_hours=model.labor_hours,
        parts=tuple(
            JobPart(part.part_number, part.description, part.quantity, part.unit_price)
            for part in model.parts
        ),
        make=model.make,
        engine=model.engine,
        requires_diagnosis=model.requires_diagnosis,
        vmrs_code=model.vmrs_code,
    )


class SqlAlchemyJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_for_problem(self, problem: ProblemType) -> list[Job]:
        try:
            async with self._session_factory() as session:
                models = await session.scalars(
                    select(JobModel).where(JobModel.problem == problem.value)
                )
                return [job_from_model(model) for model in models]
        except (SQLAlchemyError, OSError) as exc:
            raise StorageUnavailableError from exc
