"""Experiment run lifecycle contracts, separate from immutable configuration."""

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from bizora.contracts.experiment import ExperimentConfig, ResultKind


class RunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES: frozenset[RunState] = frozenset(
    {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
)

ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.PENDING: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.RUNNING: frozenset(
        {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


def is_terminal(state: RunState) -> bool:
    """Return whether a run state is final and immutable."""
    return state in TERMINAL_STATES


def is_valid_transition(from_state: RunState, to_state: RunState) -> bool:
    """Return whether a state transition is allowed."""
    return to_state in ALLOWED_TRANSITIONS[from_state]


class ExperimentRun(BaseModel):
    """One lifecycle view of an experiment run bound to an exact config."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    config: ExperimentConfig
    state: RunState = RunState.PENDING
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    error: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_lifecycle_timestamps(self) -> "ExperimentRun":
        created: datetime = self.created_at
        if self.state == RunState.PENDING:
            if self.started_at is not None or self.finished_at is not None:
                raise ValueError("A pending run must not have start or finish timestamps")
        elif self.state == RunState.RUNNING:
            if self.started_at is None:
                raise ValueError("A running run must have a start timestamp")
            if self.finished_at is not None:
                raise ValueError("A running run must not have a finish timestamp")
            if self.started_at < created:
                raise ValueError("started_at must not precede created_at")
        else:
            if self.finished_at is None:
                raise ValueError("A terminal run must have a finish timestamp")
            if self.finished_at < created:
                raise ValueError("finished_at must not precede created_at")
            if self.started_at is not None and self.finished_at < self.started_at:
                raise ValueError("finished_at must not precede started_at")
            if self.state in (RunState.SUCCEEDED, RunState.FAILED) and self.started_at is None:
                raise ValueError("A succeeded or failed run must have a start timestamp")

        if self.error is not None and self.state not in (
            RunState.FAILED,
            RunState.CANCELLED,
        ):
            raise ValueError("Only failed or cancelled runs may carry an error message")
        return self


class CreateExperimentRunRequest(BaseModel):
    """Request payload for creating a run from an exact config snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    config: ExperimentConfig


class TransitionExperimentRunRequest(BaseModel):
    """Request payload for moving a run to a new lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    to_state: RunState
    error: str | None = Field(default=None, max_length=2000)


class MetricRecord(BaseModel):
    """Extension-point contract for a future persisted metric value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    value: float
    result_kind: ResultKind


class ArtifactRecord(BaseModel):
    """Extension-point contract for a future persisted run artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    uri: str = Field(min_length=1, max_length=1024)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    result_kind: ResultKind
