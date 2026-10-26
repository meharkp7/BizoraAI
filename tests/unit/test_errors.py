
"""Tests for Bizora's standardized application errors."""

from bizora.core.errors import (
    ArchitectureCompatibilityError,
    BizoraError,
    ErrorCode,
    ExperimentStateError,
    GraphValidationError,
)


def test_base_error_preserves_code_message_and_details() -> None:
    error = BizoraError(
        ErrorCode.INVALID_REQUEST,
        "The request is invalid.",
        details={"field": "project_id"},
    )

    assert error.code == ErrorCode.INVALID_REQUEST
    assert error.message == "The request is invalid."
    assert error.details == {"field": "project_id"}


def test_error_serializes_to_json_compatible_dictionary() -> None:
    error = BizoraError(
        ErrorCode.RESOURCE_NOT_FOUND,
        "Project not found.",
        details={"resource_type": "project"},
    )

    assert error.to_dict() == {
        "code": "RESOURCE_NOT_FOUND",
        "message": "Project not found.",
        "details": {"resource_type": "project"},
    }


def test_error_without_details_uses_empty_dictionary() -> None:
    error = BizoraError(ErrorCode.INTERNAL_ERROR, "Unexpected error.")

    assert error.details == {}
    assert error.to_dict()["details"] == {}


def test_graph_validation_error_uses_stable_code() -> None:
    error = GraphValidationError(
        "Graph contains an invalid edge.",
        details={"edge_id": "edge-17"},
    )

    assert error.code == ErrorCode.INVALID_GRAPH
    assert error.details["edge_id"] == "edge-17"


def test_architecture_compatibility_error_uses_stable_code() -> None:
    error = ArchitectureCompatibilityError(
        "Tensor shapes are incompatible.",
        details={"expected": [32, 768], "actual": [32, 512]},
    )

    assert error.code == ErrorCode.INCOMPATIBLE_ARCHITECTURE
    assert error.details["expected"] == [32, 768]


def test_experiment_state_error_supports_custom_code() -> None:
    error = ExperimentStateError(
        "The experiment exceeds its resource limit.",
        code=ErrorCode.EXPERIMENT_LIMIT_EXCEEDED,
    )

    assert error.code == ErrorCode.EXPERIMENT_LIMIT_EXCEEDED


def test_errors_are_standard_python_exceptions() -> None:
    error = GraphValidationError("Invalid methodology graph.")

    assert isinstance(error, Exception)
    assert str(error) == "Invalid methodology graph."
