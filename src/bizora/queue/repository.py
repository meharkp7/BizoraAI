"""Repository operations for durable background jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.contracts.queue import (
    RETRYABLE_KINDS,
    JobDefinition,
    JobKind,
    JobState,
    JobView,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.queue.models import JobRecordRow


def _ensure_aware(value: datetime) -> datetime:
    """Return a timezone-aware timestamp, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def job_view_from_row(row: JobRecordRow) -> JobView:
    """Convert a persisted job row into its lifecycle contract."""
    return JobView(
        job_id=row.job_id,
        idempotency_key=row.idempotency_key,
        kind=JobKind(row.kind),
        state=JobState(row.state),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        payload=dict(row.payload),
        error=row.error,
        available_at=_ensure_aware(row.available_at),
        created_at=_ensure_aware(row.created_at),
        started_at=_ensure_aware(row.started_at) if row.started_at else None,
        finished_at=_ensure_aware(row.finished_at) if row.finished_at else None,
    )


def get_job(session: Session, job_id: str) -> JobRecordRow | None:
    """Retrieve one job by its identifier."""
    return session.scalar(select(JobRecordRow).where(JobRecordRow.job_id == job_id))


def get_job_by_idempotency_key(
    session: Session, idempotency_key: str
) -> JobRecordRow | None:
    """Retrieve one job by its idempotency key."""
    return session.scalar(
        select(JobRecordRow).where(
            JobRecordRow.idempotency_key == idempotency_key
        )
    )


def enqueue_job(
    session: Session,
    definition: JobDefinition,
    *,
    now: datetime,
) -> JobRecordRow:
    """Stage a job; re-enqueue with the same key returns the existing row.

    Reusing an idempotency key for a *different* job id is a caller bug
    and raises RESOURCE_CONFLICT instead of merging unrelated work.
    """
    row = JobRecordRow(
        job_id=definition.job_id,
        idempotency_key=definition.idempotency_key,
        kind=definition.kind.value,
        state=JobState.PENDING.value,
        attempts=0,
        max_attempts=definition.max_attempts,
        payload=dict(definition.payload),
        available_at=now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        existing = get_job_by_idempotency_key(session, definition.idempotency_key)
        if existing is not None and existing.job_id == definition.job_id:
            return existing
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "The job conflicts with an existing database record.",
            details={"job_id": definition.job_id},
        ) from exc
    return row


def list_claimable_jobs(
    session: Session,
    *,
    kinds: tuple[JobKind, ...] | None,
    now: datetime,
    limit: int = 10,
) -> list[JobRecordRow]:
    """List due pending jobs oldest-available-first for worker polling."""
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    statement = (
        select(JobRecordRow)
        .where(
            JobRecordRow.state == JobState.PENDING.value,
            JobRecordRow.available_at <= now,
        )
        .order_by(JobRecordRow.available_at.asc())
        .limit(limit)
    )
    if kinds is not None:
        statement = statement.where(
            JobRecordRow.kind.in_([kind.value for kind in kinds])
        )
    return list(session.scalars(statement))


def claim_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> JobRecordRow | None:
    """Atomically claim one due pending job; attempts increment on claim."""
    if lease_ttl_seconds < 1:
        raise ValueError("lease_ttl_seconds must be a positive integer.")
    result = session.connection().execute(
        update(JobRecordRow)
        .where(
            JobRecordRow.job_id == job_id,
            JobRecordRow.state == JobState.PENDING.value,
            JobRecordRow.available_at <= now,
        )
        .values(
            state=JobState.RUNNING.value,
            started_at=now,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_ttl_seconds),
            attempts=JobRecordRow.attempts + 1,
        )
    )
    if result.rowcount != 1:
        return None
    session.flush()
    row = get_job(session, job_id)
    if row is not None:
        session.refresh(row)
    return row


def heartbeat_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> JobRecordRow | None:
    """Extend the lease only when the worker still owns a running job."""
    if lease_ttl_seconds < 1:
        raise ValueError("lease_ttl_seconds must be a positive integer.")
    result = session.connection().execute(
        update(JobRecordRow)
        .where(
            JobRecordRow.job_id == job_id,
            JobRecordRow.state == JobState.RUNNING.value,
            JobRecordRow.worker_id == worker_id,
        )
        .values(lease_expires_at=now + timedelta(seconds=lease_ttl_seconds))
    )
    if result.rowcount != 1:
        return None
    session.flush()
    row = get_job(session, job_id)
    if row is not None:
        session.refresh(row)
    return row


def complete_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    now: datetime,
) -> JobRecordRow | None:
    """Finalize a worker-owned running job as succeeded."""
    result = session.connection().execute(
        update(JobRecordRow)
        .where(
            JobRecordRow.job_id == job_id,
            JobRecordRow.state == JobState.RUNNING.value,
            JobRecordRow.worker_id == worker_id,
        )
        .values(state=JobState.SUCCEEDED.value, finished_at=now, error=None)
    )
    if result.rowcount != 1:
        return None
    session.flush()
    row = get_job(session, job_id)
    if row is not None:
        session.refresh(row)
    return row


def fail_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    now: datetime,
    error: str,
    retry_in_seconds: int = 60,
) -> JobRecordRow | None:
    """Fail a job, rescheduling it only when policy allows a retry.

    A job returns to pending only when its kind is retryable and its
    attempt budget is unspent; experiment-run jobs always fail terminally
    per ADR 0003.
    """
    if retry_in_seconds < 0:
        raise ValueError("retry_in_seconds must be non-negative.")
    row = get_job(session, job_id)
    if (
        row is None
        or row.state != JobState.RUNNING.value
        or row.worker_id != worker_id
    ):
        return None
    retryable = (
        JobKind(row.kind) in RETRYABLE_KINDS and row.attempts < row.max_attempts
    )
    if retryable:
        values = {
            "state": JobState.PENDING.value,
            "error": error[:2000],
            "worker_id": None,
            "lease_expires_at": None,
            "available_at": now + timedelta(seconds=retry_in_seconds),
        }
    else:
        values = {
            "state": JobState.FAILED.value,
            "error": error[:2000],
            "finished_at": now,
        }
    session.connection().execute(
        update(JobRecordRow)
        .where(
            JobRecordRow.job_id == job_id,
            JobRecordRow.state == JobState.RUNNING.value,
            JobRecordRow.worker_id == worker_id,
        )
        .values(**values)
    )
    session.flush()
    updated = get_job(session, job_id)
    if updated is not None:
        session.refresh(updated)
    return updated


def cancel_job(
    session: Session,
    *,
    job_id: str,
    now: datetime,
) -> JobRecordRow | None:
    """Move a pending or running job to cancelled; terminal jobs stay put."""
    row = get_job(session, job_id)
    if row is None or JobState(row.state) not in (
        JobState.PENDING,
        JobState.RUNNING,
    ):
        return None
    session.connection().execute(
        update(JobRecordRow)
        .where(
            JobRecordRow.job_id == job_id,
            JobRecordRow.state.in_(
                [JobState.PENDING.value, JobState.RUNNING.value]
            ),
        )
        .values(state=JobState.CANCELLED.value, finished_at=now)
    )
    session.flush()
    updated = get_job(session, job_id)
    if updated is not None:
        session.refresh(updated)
    return updated
