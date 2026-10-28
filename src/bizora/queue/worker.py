"""Polling worker that dispatches durable jobs to handlers.

Handlers must be idempotent: a crash between handler success and
finalization can redeliver the same job after its lease expires. The
worker passes the stable idempotency key in every JobView so handlers
can deduplicate their own side effects.
"""

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from bizora.contracts.queue import JobKind, JobOutcome, JobView
from bizora.queue.repository import (
    claim_job,
    complete_job,
    fail_job,
    job_view_from_row,
    list_claimable_jobs,
)


@runtime_checkable
class JobHandler(Protocol):
    """Interface implemented by every per-kind job handler."""

    @property
    def handled_kind(self) -> JobKind:
        """Return the job kind this handler processes."""
        ...

    def handle(self, job: JobView) -> JobOutcome:
        """Process one claimed job without raising for domain failures."""
        ...


@dataclass(frozen=True)
class WorkerConfig:
    """Tuning knobs for one queue worker."""

    worker_id: str
    lease_ttl_seconds: int = 300
    poll_seconds: float = 0.5
    retry_delay_seconds: int = 60

    def __post_init__(self) -> None:
        """Reject unusable worker tuning values."""
        if not self.worker_id:
            raise ValueError("worker_id must be non-empty.")
        if self.lease_ttl_seconds < 1:
            raise ValueError("lease_ttl_seconds must be positive.")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive.")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative.")


class JobWorker:
    """Claim due jobs and dispatch them to registered handlers."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        config: WorkerConfig,
        handlers: Mapping[JobKind, JobHandler] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._handlers: dict[JobKind, JobHandler] = dict(handlers or {})

    def register(self, handler: JobHandler) -> None:
        """Add a handler; duplicate kinds are wiring bugs."""
        if handler.handled_kind in self._handlers:
            raise ValueError(
                f"Handler for '{handler.handled_kind.value}' is already registered."
            )
        self._handlers[handler.handled_kind] = handler

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Yield a session that always closes after use."""
        session = self._session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _utcnow() -> datetime:
        """Return the current timezone-aware UTC time."""
        return datetime.now(UTC)

    def run_once(self) -> str | None:
        """Claim and dispatch one due job; return its id or None."""
        with self._session() as session:
            candidates = [
                row.job_id
                for row in list_claimable_jobs(
                    session, kinds=None, now=self._utcnow(), limit=10
                )
            ]
        for job_id in candidates:
            with self._session() as session:
                claimed = claim_job(
                    session,
                    job_id=job_id,
                    worker_id=self._config.worker_id,
                    now=self._utcnow(),
                    lease_ttl_seconds=self._config.lease_ttl_seconds,
                )
                if claimed is None:
                    continue
                view = job_view_from_row(claimed)
                session.commit()
            self._dispatch(view)
            return view.job_id
        return None

    def drain(self, *, max_jobs: int = 100) -> int:
        """Process due jobs until none remain or the cap is reached."""
        if max_jobs < 1:
            raise ValueError("max_jobs must be a positive integer.")
        processed = 0
        while processed < max_jobs:
            if self.run_once() is None:
                return processed
            processed += 1
            time.sleep(self._config.poll_seconds)
        return processed

    def _dispatch(self, job: JobView) -> None:
        """Run one claimed job's handler and finalize its outcome."""
        handler = self._handlers.get(job.kind)
        if handler is None:
            self._record_failure(
                job,
                f"No handler registered for job kind '{job.kind.value}'.",
                retry_in_seconds=None,
            )
            return
        try:
            outcome = handler.handle(job)
        except Exception as exc:
            self._record_failure(job, f"Handler raised: {exc!r}"[:2000], None)
            return
        if outcome.status == "succeeded":
            with self._session() as session:
                complete_job(
                    session,
                    job_id=job.job_id,
                    worker_id=self._config.worker_id,
                    now=self._utcnow(),
                )
                session.commit()
        else:
            assert outcome.error is not None  # validated by the contract
            self._record_failure(
                job, outcome.error, retry_in_seconds=outcome.retry_in_seconds
            )

    def _record_failure(
        self, job: JobView, error: str, retry_in_seconds: int | None
    ) -> None:
        """Fail one job, honoring a handler-requested retry delay."""
        delay = (
            retry_in_seconds
            if retry_in_seconds is not None
            else self._config.retry_delay_seconds
        )
        with self._session() as session:
            fail_job(
                session,
                job_id=job.job_id,
                worker_id=self._config.worker_id,
                now=self._utcnow(),
                error=error,
                retry_in_seconds=delay,
            )
            session.commit()
