"""Durable job-queue contracts for ingestion and experiment runs.

The queue is durable (persisted rows, atomic claims, leases) and
dispatches idempotently. Retry policy follows ADR 0003: ingestion jobs
may retry, experiment runs never retry automatically.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class JobKind(StrEnum):
    """Pipeline stage a job belongs to; controls retry policy."""

    INGESTION = "ingestion"
    EXPERIMENT_RUN = "experiment_run"


RETRYABLE_KINDS: frozenset[JobKind] = frozenset({JobKind.INGESTION})

DEFAULT_MAX_ATTEMPTS: dict[JobKind, int] = {
    JobKind.INGESTION: 3,
    JobKind.EXPERIMENT_RUN: 1,
}


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
)


class JobDefinition(BaseModel):
    """Request payload for enqueueing one durable job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    kind: JobKind
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="before")
    @classmethod
    def apply_kind_default_attempts(cls, data: Any) -> Any:
        """Default the attempt budget from the job kind when omitted."""
        if isinstance(data, dict) and data.get("max_attempts") is None:
            raw_kind = data.get("kind")
            if isinstance(raw_kind, JobKind):
                kind = raw_kind
            elif isinstance(raw_kind, str):
                try:
                    kind = JobKind(raw_kind)
                except ValueError:
                    return data
            else:
                return data
            data = {**data, "max_attempts": DEFAULT_MAX_ATTEMPTS[kind]}
        return data

    @model_validator(mode="after")
    def validate_attempts_policy(self) -> "JobDefinition":
        if self.kind == JobKind.EXPERIMENT_RUN and self.max_attempts != 1:
            raise ValueError(
                "Experiment-run jobs must use max_attempts=1 "
                "(ADR 0003: runs are never retried)."
            )
        return self


class JobView(BaseModel):
    """Immutable lifecycle view of one enqueued job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    kind: JobKind
    state: JobState
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=2000)
    available_at: AwareDatetime
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None


class JobOutcome(BaseModel):
    """Handler-reported result for one claimed job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["succeeded", "failed"]
    error: str | None = Field(default=None, max_length=2000)
    retry_in_seconds: int | None = Field(default=None, ge=0, le=86_400)

    @model_validator(mode="after")
    def validate_outcome_consistency(self) -> "JobOutcome":
        if self.status == "failed" and self.error is None:
            raise ValueError("A failed job outcome must carry an error message.")
        if self.status == "succeeded" and (
            self.error is not None or self.retry_in_seconds is not None
        ):
            raise ValueError("A succeeded job outcome must not carry error details.")
        return self
