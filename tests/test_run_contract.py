"""Tests for experiment run lifecycle contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bizora.contracts.experiment import ResultKind
from bizora.contracts.run import (
    ALLOWED_TRANSITIONS,
    ArtifactRecord,
    ExperimentRun,
    MetricRecord,
    RunState,
    is_terminal,
    is_valid_transition,
)


def valid_experiment_data() -> dict[str, object]:
    """Return a valid experiment configuration payload."""
    return {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "hf-vit-classification",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {
            "train": 0.8,
            "validation": 0.1,
            "test": 0.1,
        },
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 1,
    }


def valid_run_data(**overrides: object) -> dict[str, object]:
    """Return a valid experiment run payload."""
    payload: dict[str, object] = {
        "run_id": "run-1",
        "config": valid_experiment_data(),
        "state": RunState.PENDING.value,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    payload.update(overrides)
    return payload


def test_run_state_values_are_explicit() -> None:
    assert RunState.PENDING.value == "pending"
    assert RunState.RUNNING.value == "running"
    assert RunState.SUCCEEDED.value == "succeeded"
    assert RunState.FAILED.value == "failed"
    assert RunState.CANCELLED.value == "cancelled"


def test_allowed_transitions_match_lifecycle() -> None:
    assert ALLOWED_TRANSITIONS[RunState.PENDING] == frozenset(
        {RunState.RUNNING, RunState.CANCELLED}
    )
    assert ALLOWED_TRANSITIONS[RunState.RUNNING] == frozenset(
        {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
    )
    assert ALLOWED_TRANSITIONS[RunState.SUCCEEDED] == frozenset()
    assert ALLOWED_TRANSITIONS[RunState.FAILED] == frozenset()
    assert ALLOWED_TRANSITIONS[RunState.CANCELLED] == frozenset()


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        (RunState.PENDING, RunState.RUNNING),
        (RunState.PENDING, RunState.CANCELLED),
        (RunState.RUNNING, RunState.SUCCEEDED),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.RUNNING, RunState.CANCELLED),
    ],
)
def test_valid_transitions_are_accepted(
    from_state: RunState, to_state: RunState
) -> None:
    assert is_valid_transition(from_state, to_state) is True


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        (RunState.PENDING, RunState.PENDING),
        (RunState.PENDING, RunState.SUCCEEDED),
        (RunState.PENDING, RunState.FAILED),
        (RunState.RUNNING, RunState.PENDING),
        (RunState.RUNNING, RunState.RUNNING),
        (RunState.SUCCEEDED, RunState.RUNNING),
        (RunState.SUCCEEDED, RunState.FAILED),
        (RunState.SUCCEEDED, RunState.CANCELLED),
        (RunState.FAILED, RunState.RUNNING),
        (RunState.FAILED, RunState.SUCCEEDED),
        (RunState.CANCELLED, RunState.RUNNING),
        (RunState.CANCELLED, RunState.PENDING),
    ],
)
def test_invalid_transitions_are_rejected(
    from_state: RunState, to_state: RunState
) -> None:
    assert is_valid_transition(from_state, to_state) is False


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (RunState.PENDING, False),
        (RunState.RUNNING, False),
        (RunState.SUCCEEDED, True),
        (RunState.FAILED, True),
        (RunState.CANCELLED, True),
    ],
)
def test_terminal_states_are_explicit(state: RunState, expected: bool) -> None:
    assert is_terminal(state) is expected


def test_pending_run_has_no_lifecycle_timestamps() -> None:
    run = ExperimentRun.model_validate(valid_run_data())

    assert run.state == RunState.PENDING
    assert run.started_at is None
    assert run.finished_at is None


def test_running_run_requires_start_timestamp() -> None:
    with pytest.raises(ValidationError, match="start timestamp"):
        ExperimentRun.model_validate(
            valid_run_data(state=RunState.RUNNING.value)
        )


def test_terminal_run_requires_finish_timestamp() -> None:
    started = datetime(2026, 1, 2, tzinfo=UTC)
    with pytest.raises(ValidationError, match="finish timestamp"):
        ExperimentRun.model_validate(
            valid_run_data(
                state=RunState.SUCCEEDED.value,
                started_at=started,
            )
        )


def test_succeeded_run_requires_start_timestamp() -> None:
    finished = datetime(2026, 1, 3, tzinfo=UTC)
    with pytest.raises(ValidationError, match="start timestamp"):
        ExperimentRun.model_validate(
            valid_run_data(
                state=RunState.SUCCEEDED.value,
                finished_at=finished,
            )
        )


def test_cancelled_run_may_skip_start_timestamp() -> None:
    finished = datetime(2026, 1, 3, tzinfo=UTC)
    run = ExperimentRun.model_validate(
        valid_run_data(
            state=RunState.CANCELLED.value,
            finished_at=finished,
        )
    )

    assert run.state == RunState.CANCELLED
    assert run.started_at is None
    assert run.finished_at == finished


def test_run_rejects_non_utc_ordered_timestamps() -> None:
    created = datetime(2026, 1, 2, tzinfo=UTC)
    started = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="must not precede"):
        ExperimentRun.model_validate(
            valid_run_data(
                state=RunState.RUNNING.value,
                created_at=created,
                started_at=started,
            )
        )


def test_run_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValidationError):
        ExperimentRun.model_validate(
            valid_run_data(created_at=datetime(2026, 1, 1))
        )


def test_run_rejects_error_on_active_states() -> None:
    started = datetime(2026, 1, 2, tzinfo=UTC)
    with pytest.raises(ValidationError, match="error message"):
        ExperimentRun.model_validate(
            valid_run_data(
                state=RunState.RUNNING.value,
                started_at=started,
                error="boom",
            )
        )


def test_failed_run_may_carry_error() -> None:
    started = datetime(2026, 1, 2, tzinfo=UTC)
    finished = datetime(2026, 1, 3, tzinfo=UTC)
    run = ExperimentRun.model_validate(
        valid_run_data(
            state=RunState.FAILED.value,
            started_at=started,
            finished_at=finished,
            error="worker timeout",
        )
    )

    assert run.error == "worker timeout"


def test_run_configuration_is_immutable() -> None:
    run = ExperimentRun.model_validate(valid_run_data())

    with pytest.raises(ValidationError):
        run.__setattr__("state", RunState.RUNNING)


def test_run_rejects_unexpected_fields() -> None:
    payload = valid_run_data()
    payload["unreviewed_field"] = True

    with pytest.raises(ValidationError):
        ExperimentRun.model_validate(payload)


def test_metric_record_requires_explicit_result_kind() -> None:
    metric = MetricRecord.model_validate(
        {
            "metric_id": "metric-1",
            "run_id": "run-1",
            "name": "accuracy",
            "value": 0.92,
            "result_kind": ResultKind.MEASURED.value,
        }
    )

    assert metric.result_kind == ResultKind.MEASURED


def test_artifact_record_requires_explicit_result_kind() -> None:
    artifact = ArtifactRecord.model_validate(
        {
            "artifact_id": "artifact-1",
            "run_id": "run-1",
            "kind": "checkpoint",
            "uri": "s3://bizora/artifacts/run-1/checkpoint",
            "result_kind": ResultKind.MEASURED.value,
        }
    )

    assert artifact.result_kind == ResultKind.MEASURED
    assert artifact.sha256 is None
