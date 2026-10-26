
"""Stable, provider-independent application errors."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Machine-readable error codes shared across Bizora services."""

    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    INVALID_REQUEST = "INVALID_REQUEST"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    INVALID_GRAPH = "INVALID_GRAPH"
    INVALID_GRAPH_PATCH = "INVALID_GRAPH_PATCH"
    INCOMPATIBLE_ARCHITECTURE = "INCOMPATIBLE_ARCHITECTURE"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    EXPERIMENT_LIMIT_EXCEEDED = "EXPERIMENT_LIMIT_EXCEEDED"
    EXPERIMENT_NOT_READY = "EXPERIMENT_NOT_READY"
    EXPERIMENT_FAILED = "EXPERIMENT_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_REQUEST_FAILED = "PROVIDER_REQUEST_FAILED"
    UPLOAD_REJECTED = "UPLOAD_REJECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class BizoraError(Exception):
    """Base exception for expected, application-level failures."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable error representation for trusted API handlers."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(BizoraError):
    """Raised when required application configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_CONFIGURATION, message)


class GraphValidationError(BizoraError):
    """Raised when a methodology graph violates its contract."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(ErrorCode.INVALID_GRAPH, message, details=details)


class ArchitectureCompatibilityError(BizoraError):
    """Raised when a proposed architecture change cannot be compiled safely."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.INCOMPATIBLE_ARCHITECTURE,
            message,
            details=details,
        )


class ExperimentStateError(BizoraError):
    """Raised when an experiment action is invalid for its current state."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.EXPERIMENT_NOT_READY,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, details=details)
