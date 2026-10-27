"""Execution boundary contracts for controlled experiment runs."""

import json
import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import MethodologyGraph


class ExecutionErrorCode(StrEnum):
    ADAPTER_UNKNOWN = "adapter_unknown"
    ADAPTER_INCOMPATIBLE = "adapter_incompatible"
    GRAPH_MISMATCH = "graph_mismatch"
    TIMEOUT = "timeout"
    MEMORY_SOFT_LIMIT = "memory_soft_limit"
    ADAPTER_FAILED = "adapter_failed"
    RESULT_INVALID = "result_invalid"
    LEASE_EXPIRED = "lease_expired"
    ISOLATION_UNAVAILABLE = "isolation_unavailable"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StructuredError(BaseModel):
    """Machine-readable failure detail recorded for a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ExecutionErrorCode
    message: str = Field(min_length=1, max_length=2000)
    exit_code: int | None = None
    signal: int | None = Field(default=None, ge=0)

    def to_record_value(self) -> str:
        """Serialize to the bounded run-record error format."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "exit_code": self.exit_code,
            "signal": self.signal,
        }
        return json.dumps(payload, sort_keys=True)[:2000]


class ExecutionLimits(BaseModel):
    """Resource bounds enforced around one adapter execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: int = Field(ge=1, le=86_400)
    cpu_seconds: int = Field(ge=1, le=86_400)
    soft_rss_mb: int = Field(ge=1)
    max_output_bytes: int = Field(ge=1024, le=100_000_000)
    kill_grace_seconds: int = Field(ge=0, le=300)


class AdapterExecutionRequest(BaseModel):
    """Immutable inputs handed to one adapter execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    config: ExperimentConfig
    graph: MethodologyGraph
    limits: ExecutionLimits

    @model_validator(mode="after")
    def validate_request_binding(self) -> "AdapterExecutionRequest":
        config = self.config
        graph = self.graph
        if (
            config.project_id != graph.project_id
            or config.graph_id != graph.graph_id
            or config.graph_version != graph.version
        ):
            raise ValueError(
                "Request config must reference the exact supplied graph revision."
            )
        return self


class ReproducibilityEcho(BaseModel):
    """Adapter-observed reproducibility fields, echoed back for verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: str = Field(min_length=1, max_length=128)
    adapter_version: str = Field(min_length=1, max_length=64)
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_revision: str = Field(min_length=1, max_length=128)
    code_revision: str = Field(min_length=7, max_length=64)
    seed: int = Field(ge=0, le=2**32 - 1)
    graph_id: str = Field(min_length=1, max_length=128)
    graph_version: int = Field(ge=1)


class ReportedMetric(BaseModel):
    """One adapter-reported metric value, keyed by the adapter's metric id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    value: float
    result_kind: ResultKind

    @model_validator(mode="after")
    def validate_finite_value(self) -> "ReportedMetric":
        if not math.isfinite(self.value):
            raise ValueError("Metric values must be finite.")
        return self


class ReportedArtifact(BaseModel):
    """One adapter-reported artifact reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    uri: str = Field(min_length=1, max_length=1024)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    result_kind: ResultKind


class ExecutionResult(BaseModel):
    """Outcome of one adapter execution with its reported results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    status: ExecutionStatus
    echo: ReproducibilityEcho
    diagnostics: tuple[str, ...] = Field(default=(), max_length=32)
    metrics: tuple[ReportedMetric, ...] = Field(default=(), max_length=100)
    artifacts: tuple[ReportedArtifact, ...] = Field(default=(), max_length=100)
    error: StructuredError | None = None

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "ExecutionResult":
        for entry in self.diagnostics:
            if len(entry) > 2000:
                raise ValueError("Diagnostic entries must be at most 2000 characters.")
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("Reported metric ids must be unique within a result.")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Reported artifact ids must be unique within a result.")
        if self.status == ExecutionStatus.FAILED and self.error is None:
            raise ValueError("A failed execution result must carry a structured error.")
        if self.status == ExecutionStatus.SUCCEEDED and self.error is not None:
            raise ValueError("A succeeded execution result must not carry an error.")
        return self
