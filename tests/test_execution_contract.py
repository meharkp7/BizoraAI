"""Tests for execution boundary contracts."""

import pytest
from pydantic import ValidationError

from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionResult,
    ExecutionStatus,
    ReproducibilityEcho,
    StructuredError,
)


def valid_config_data() -> dict[str, object]:
    """Return a valid experiment configuration payload."""
    return {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "bizora.deterministic-test",
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
        "max_gpu_count": 0,
    }


def valid_graph_data() -> dict[str, object]:
    """Return a minimal valid methodology graph payload."""
    return {
        "project_id": "project-1",
        "graph_id": "graph-1",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-1"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
            {"id": "output", "kind": "output", "label": "Predictions"},
        ],
        "edges": [
            {"id": "edge-1", "source": "input", "target": "encoder"},
            {"id": "edge-2", "source": "encoder", "target": "output"},
        ],
        "created_by": "researcher-1",
    }


def valid_limits_data() -> dict[str, object]:
    """Return valid execution limits."""
    return {
        "timeout_seconds": 600,
        "cpu_seconds": 600,
        "soft_rss_mb": 512,
        "max_output_bytes": 1_000_000,
        "kill_grace_seconds": 10,
    }


def valid_echo_data() -> dict[str, object]:
    """Return a valid reproducibility echo."""
    return {
        "adapter_id": "bizora.deterministic-test",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "code_revision": "abcdef1",
        "seed": 42,
        "graph_id": "graph-1",
        "graph_version": 1,
    }


def valid_request_data() -> dict[str, object]:
    """Return a valid adapter execution request payload."""
    return {
        "run_id": "run-1",
        "config": valid_config_data(),
        "graph": valid_graph_data(),
        "limits": valid_limits_data(),
    }


def valid_error_data() -> dict[str, object]:
    """Return a valid structured error payload."""
    return {
        "code": ExecutionErrorCode.ADAPTER_FAILED.value,
        "message": "Adapter exited with status 1.",
        "exit_code": 1,
    }


def test_execution_error_codes_are_explicit() -> None:
    assert ExecutionErrorCode.TIMEOUT.value == "timeout"
    assert ExecutionErrorCode.ADAPTER_UNKNOWN.value == "adapter_unknown"
    assert ExecutionErrorCode.ADAPTER_INCOMPATIBLE.value == "adapter_incompatible"
    assert ExecutionErrorCode.GRAPH_MISMATCH.value == "graph_mismatch"
    assert ExecutionErrorCode.LEASE_EXPIRED.value == "lease_expired"


def test_structured_error_accepts_exit_detail() -> None:
    error = StructuredError.model_validate(valid_error_data())

    assert error.code == ExecutionErrorCode.ADAPTER_FAILED
    assert error.exit_code == 1
    assert error.signal is None


def test_execution_limits_accept_valid_bounds() -> None:
    limits = ExecutionLimits.model_validate(valid_limits_data())

    assert limits.timeout_seconds == 600
    assert limits.kill_grace_seconds == 10


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 0),
        ("timeout_seconds", 86_401),
        ("cpu_seconds", 0),
        ("soft_rss_mb", 0),
        ("max_output_bytes", 1023),
        ("max_output_bytes", 100_000_001),
        ("kill_grace_seconds", -1),
        ("kill_grace_seconds", 301),
    ],
)
def test_execution_limits_reject_invalid_bounds(
    field: str, value: object
) -> None:
    payload = valid_limits_data()
    payload[field] = value

    with pytest.raises(ValidationError):
        ExecutionLimits.model_validate(payload)


def test_request_binds_config_to_exact_graph_revision() -> None:
    request = AdapterExecutionRequest.model_validate(valid_request_data())

    assert request.run_id == "run-1"
    assert request.config.graph_version == request.graph.version


@pytest.mark.parametrize(
    "field",
    ["project_id", "graph_id", "graph_version"],
)
def test_request_rejects_graph_mismatch(field: str) -> None:
    payload = valid_request_data()
    config = valid_config_data()
    if field == "graph_version":
        config[field] = 2
    else:
        config[field] = "other"
    payload["config"] = config

    with pytest.raises(ValidationError, match="exact supplied graph revision"):
        AdapterExecutionRequest.model_validate(payload)


def test_succeeded_result_requires_no_error() -> None:
    result = ExecutionResult.model_validate(
        {
            "run_id": "run-1",
            "status": ExecutionStatus.SUCCEEDED.value,
            "echo": valid_echo_data(),
            "diagnostics": ["validated 3 nodes, 2 edges"],
        }
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.error is None


def test_failed_result_requires_structured_error() -> None:
    with pytest.raises(ValidationError, match="structured error"):
        ExecutionResult.model_validate(
            {
                "run_id": "run-1",
                "status": ExecutionStatus.FAILED.value,
                "echo": valid_echo_data(),
            }
        )


def test_succeeded_result_rejects_error() -> None:
    with pytest.raises(ValidationError, match="must not carry an error"):
        ExecutionResult.model_validate(
            {
                "run_id": "run-1",
                "status": ExecutionStatus.SUCCEEDED.value,
                "echo": valid_echo_data(),
                "error": valid_error_data(),
            }
        )


def test_result_rejects_too_many_diagnostics() -> None:
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(
            {
                "run_id": "run-1",
                "status": ExecutionStatus.SUCCEEDED.value,
                "echo": valid_echo_data(),
                "diagnostics": [f"line {index}" for index in range(33)],
            }
        )


def test_result_rejects_oversized_diagnostic_entry() -> None:
    with pytest.raises(ValidationError, match="at most 2000 characters"):
        ExecutionResult.model_validate(
            {
                "run_id": "run-1",
                "status": ExecutionStatus.SUCCEEDED.value,
                "echo": valid_echo_data(),
                "diagnostics": ["x" * 2001],
            }
        )


def test_result_carries_no_metric_values() -> None:
    assert "metrics" not in ExecutionResult.model_fields
    assert "metric_values" not in ExecutionResult.model_fields


def test_execution_contracts_are_immutable() -> None:
    result = ExecutionResult.model_validate(
        {
            "run_id": "run-1",
            "status": ExecutionStatus.SUCCEEDED.value,
            "echo": valid_echo_data(),
        }
    )

    with pytest.raises(ValidationError):
        result.__setattr__("status", ExecutionStatus.FAILED)


def test_execution_contracts_reject_unexpected_fields() -> None:
    payload = valid_limits_data()
    payload["unreviewed_setting"] = True

    with pytest.raises(ValidationError):
        ExecutionLimits.model_validate(payload)


def test_echo_round_trips_reproducibility_fields() -> None:
    echo = ReproducibilityEcho.model_validate(valid_echo_data())

    assert echo.seed == 42
    assert echo.dataset_revision == "sha256:example"
    assert echo.code_revision == "abcdef1"
    assert echo.graph_version == 1
