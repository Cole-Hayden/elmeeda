from dataclasses import replace
from decimal import Decimal

from issue_tracker.domain.issue import ProblemType
from issue_tracker.domain.job import Job, select_job
from issue_tracker.infrastructure.mock_data import COOLANT_LEAK_JOB, JOBS, TRUCK_118, TRUCK_214

GENERIC = COOLANT_LEAK_JOB
MAKE = replace(GENERIC, job_code="MAKE", make="Freightliner", labor_hours=Decimal("3.0"))
MAKE_AND_ENGINE = replace(MAKE, job_code="MAKE_ENGINE", engine="DD15")
OTHER_ENGINE = replace(MAKE, job_code="OTHER_ENGINE", engine="OTHER")


def select(*jobs: Job) -> Job | None:
    return select_job(jobs, ProblemType.COOLANT_LEAK, TRUCK_214)


def test_generic_job_is_used_when_nothing_more_specific_matches() -> None:
    assert select(GENERIC) == GENERIC


def test_make_job_beats_generic() -> None:
    assert select(GENERIC, MAKE) == MAKE


def test_make_and_engine_job_beats_make() -> None:
    assert select(MAKE_AND_ENGINE, GENERIC, MAKE) == MAKE_AND_ENGINE


def test_job_for_another_engine_does_not_apply() -> None:
    assert select(GENERIC, OTHER_ENGINE) == GENERIC


def test_job_for_another_make_does_not_apply() -> None:
    assert select_job((GENERIC, MAKE), ProblemType.COOLANT_LEAK, TRUCK_118) == GENERIC


def test_job_for_another_problem_does_not_apply() -> None:
    assert select_job((GENERIC,), ProblemType.BRAKE_FAILURE, TRUCK_214) is None


def test_unknown_problem_selects_a_diagnostic_job_with_no_parts() -> None:
    job = select_job(JOBS, ProblemType.UNKNOWN, TRUCK_214)

    assert job is not None
    assert job.requires_diagnosis is True
    assert job.parts == ()
