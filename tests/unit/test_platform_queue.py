"""Tests for the durable job queue and worker.

Self-contained: all persistence runs on in-memory SQLite, and every
handler in this file is an explicitly-marked test fake.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from bizora.contracts.queue import (
    JobDefinition,
    JobKind,
    JobOutcome,
    JobState,
    JobView,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base
from bizora.queue.repository import (
    cancel_job,
    claim_job,
    complete_job,
    enqueue_job,
    fail_job,
    get_job,
    heartbeat_job,
    list_claimable_jobs,
)
from bizora.queue.worker import JobHandler, JobWorker, WorkerConfig


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a factory for short-lived sessions."""
    return lambda: Session(engine)


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Yield one session bound to the test database."""
    with Session(engine) as session:
        yield session


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


def make_definition(
    job_id: str = "job-1",
    key: str = "key-1",
    kind: JobKind = JobKind.INGESTION,
    **overrides: Any,
) -> JobDefinition:
    """Build a job definition, retargetable per test."""
    payload: dict[str, Any] = {
        "job_id": job_id,
        "idempotency_key": key,
        "kind": kind,
        "payload": {"source": "fake-test-source"},
    }
    payload.update(overrides)
    return JobDefinition.model_validate(payload)


class FakeHandler:
    """Test-only handler recording every dispatch."""

    def __init__(self, kind: JobKind, outcome: JobOutcome) -> None:
        self._kind = kind
        self._outcome = outcome
        self.calls: list[JobView] = []

    @property
    def handled_kind(self) -> JobKind:
        return self._kind

    def handle(self, job: JobView) -> JobOutcome:
        self.calls.append(job)
        return self._outcome


class ExplodingFakeHandler:
    """Test-only handler simulating an unexpected crash."""

    handled_kind = JobKind.INGESTION

    def handle(self, job: JobView) -> JobOutcome:
        raise RuntimeError("fake handler crash")


def test_definition_attempt_defaults_follow_retry_policy() -> None:
    ingestion = make_definition(kind=JobKind.INGESTION)
    run = make_definition(job_id="job-2", key="key-2", kind=JobKind.EXPERIMENT_RUN)

    assert ingestion.max_attempts == 3
    assert run.max_attempts == 1

    with pytest.raises(ValidationError):
        make_definition(
            job_id="job-3",
            key="key-3",
            kind=JobKind.EXPERIMENT_RUN,
            max_attempts=3,
        )


def test_outcome_contract_requires_consistent_fields() -> None:
    with pytest.raises(ValidationError):
        JobOutcome(status="failed")
    with pytest.raises(ValidationError):
        JobOutcome(status="succeeded", error="unexpected")
    assert JobOutcome(status="succeeded").status == "succeeded"


def test_enqueue_is_idempotent_on_idempotency_key(session: Session) -> None:
    first = enqueue_job(session, make_definition(), now=utcnow())
    session.commit()
    second = enqueue_job(session, make_definition(), now=utcnow())
    session.commit()

    assert first.id == second.id

    with pytest.raises(BizoraError) as exc_info:
        enqueue_job(
            session,
            make_definition(job_id="different-job", key="key-1"),
            now=utcnow(),
        )
    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT


def test_claim_is_atomic_and_increments_attempts(session: Session) -> None:
    enqueue_job(session, make_definition(), now=utcnow())
    session.commit()

    claimed = claim_job(
        session, job_id="job-1", worker_id="worker-a", now=utcnow(),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    assert claimed.state == JobState.RUNNING.value
    assert claimed.attempts == 1
    assert claimed.worker_id == "worker-a"
    session.commit()

    again = claim_job(
        session, job_id="job-1", worker_id="worker-b", now=utcnow(),
        lease_ttl_seconds=300,
    )
    assert again is None


def test_delayed_jobs_are_not_claimable_until_due(session: Session) -> None:
    enqueue_job(session, make_definition(), now=utcnow())
    session.commit()
    claimed = claim_job(
        session, job_id="job-1", worker_id="worker-a", now=utcnow(),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    failed = fail_job(
        session, job_id="job-1", worker_id="worker-a", now=utcnow(),
        error="fake transient failure", retry_in_seconds=3600,
    )
    assert failed is not None
    assert failed.state == JobState.PENDING.value
    session.commit()

    assert list_claimable_jobs(session, kinds=None, now=utcnow()) == []
    assert (
        claim_job(
            session, job_id="job-1", worker_id="worker-b", now=utcnow(),
            lease_ttl_seconds=300,
        )
        is None
    )


def test_ingestion_retries_until_budget_then_fails(session: Session) -> None:
    enqueue_job(session, make_definition(max_attempts=2), now=utcnow())
    session.commit()

    first = claim_job(
        session, job_id="job-1", worker_id="w", now=utcnow(), lease_ttl_seconds=60
    )
    assert first is not None and first.attempts == 1
    rescheduled = fail_job(
        session, job_id="job-1", worker_id="w", now=utcnow(),
        error="fake attempt one", retry_in_seconds=0,
    )
    assert rescheduled is not None
    assert rescheduled.state == JobState.PENDING.value
    session.commit()

    second = claim_job(
        session, job_id="job-1", worker_id="w", now=utcnow(), lease_ttl_seconds=60
    )
    assert second is not None and second.attempts == 2
    terminal = fail_job(
        session, job_id="job-1", worker_id="w", now=utcnow(),
        error="fake attempt two", retry_in_seconds=0,
    )
    assert terminal is not None
    assert terminal.state == JobState.FAILED.value
    assert terminal.finished_at is not None


def test_experiment_run_jobs_never_retry(session: Session) -> None:
    enqueue_job(
        session,
        make_definition(job_id="run-job", key="run-key", kind=JobKind.EXPERIMENT_RUN),
        now=utcnow(),
    )
    session.commit()
    claimed = claim_job(
        session, job_id="run-job", worker_id="w", now=utcnow(), lease_ttl_seconds=60
    )
    assert claimed is not None

    terminal = fail_job(
        session, job_id="run-job", worker_id="w", now=utcnow(),
        error="fake run failure", retry_in_seconds=0,
    )

    assert terminal is not None
    assert terminal.state == JobState.FAILED.value


def test_complete_heartbeat_and_cancel(session: Session) -> None:
    enqueue_job(session, make_definition(), now=utcnow())
    enqueue_job(session, make_definition(job_id="job-2", key="key-2"), now=utcnow())
    session.commit()

    claimed = claim_job(
        session, job_id="job-1", worker_id="w", now=utcnow(), lease_ttl_seconds=60
    )
    assert claimed is not None
    assert (
        heartbeat_job(
            session, job_id="job-1", worker_id="other",
            now=utcnow(), lease_ttl_seconds=60,
        )
        is None
    )
    assert (
        heartbeat_job(
            session, job_id="job-1", worker_id="w",
            now=utcnow(), lease_ttl_seconds=60,
        )
        is not None
    )
    done = complete_job(session, job_id="job-1", worker_id="w", now=utcnow())
    assert done is not None and done.state == JobState.SUCCEEDED.value

    cancelled = cancel_job(session, job_id="job-2", now=utcnow())
    assert cancelled is not None and cancelled.state == JobState.CANCELLED.value
    assert cancel_job(session, job_id="job-1", now=utcnow()) is None


def test_worker_dispatches_and_finalizes(
    session_factory: Callable[[], Session],
) -> None:
    session = session_factory()
    try:
        enqueue_job(session, make_definition(), now=utcnow())
        session.commit()
    finally:
        session.close()

    handler = FakeHandler(JobKind.INGESTION, JobOutcome(status="succeeded"))
    assert isinstance(handler, JobHandler)
    worker = JobWorker(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.001),
        {JobKind.INGESTION: handler},
    )

    assert worker.run_once() == "job-1"
    assert len(handler.calls) == 1
    assert handler.calls[0].idempotency_key == "key-1"
    assert worker.run_once() is None

    check = session_factory()
    try:
        row = get_job(check, "job-1")
        assert row is not None and row.state == JobState.SUCCEEDED.value
    finally:
        check.close()


def test_worker_survives_handler_crash_and_reschedules(
    session_factory: Callable[[], Session],
) -> None:
    session = session_factory()
    try:
        enqueue_job(session, make_definition(max_attempts=2), now=utcnow())
        session.commit()
    finally:
        session.close()

    worker = JobWorker(
        session_factory,
        WorkerConfig(
            worker_id="worker-a", poll_seconds=0.001, retry_delay_seconds=0
        ),
        {JobKind.INGESTION: ExplodingFakeHandler()},
    )

    assert worker.run_once() == "job-1"

    check = session_factory()
    try:
        row = get_job(check, "job-1")
        assert row is not None and row.state == JobState.PENDING.value
    finally:
        check.close()


def test_worker_fails_unknown_kind_terminally(
    session_factory: Callable[[], Session],
) -> None:
    session = session_factory()
    try:
        enqueue_job(
            session,
            make_definition(
                job_id="run-job", key="run-key", kind=JobKind.EXPERIMENT_RUN
            ),
            now=utcnow(),
        )
        session.commit()
    finally:
        session.close()

    worker = JobWorker(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.001),
    )

    assert worker.run_once() == "run-job"

    check = session_factory()
    try:
        row = get_job(check, "run-job")
        assert row is not None and row.state == JobState.FAILED.value
        assert row.error is not None and "no handler" in row.error.lower()
    finally:
        check.close()


def test_worker_rejects_duplicate_handler_kind(
    session_factory: Callable[[], Session],
) -> None:
    worker = JobWorker(
        session_factory, WorkerConfig(worker_id="w", poll_seconds=0.001)
    )
    worker.register(FakeHandler(JobKind.INGESTION, JobOutcome(status="succeeded")))
    with pytest.raises(ValueError):
        worker.register(
            FakeHandler(JobKind.INGESTION, JobOutcome(status="succeeded"))
        )


def test_worker_drain_processes_bounded_batch(
    session_factory: Callable[[], Session],
) -> None:
    session = session_factory()
    try:
        for index in range(3):
            enqueue_job(
                session,
                make_definition(job_id=f"job-{index}", key=f"key-{index}"),
                now=utcnow(),
            )
        session.commit()
    finally:
        session.close()

    worker = JobWorker(
        session_factory,
        WorkerConfig(worker_id="w", poll_seconds=0.001),
        {
            JobKind.INGESTION: FakeHandler(
                JobKind.INGESTION, JobOutcome(status="succeeded")
            )
        },
    )

    assert worker.drain(max_jobs=2) == 2
    assert worker.drain(max_jobs=10) == 1
    with pytest.raises(ValueError):
        worker.drain(max_jobs=0)
