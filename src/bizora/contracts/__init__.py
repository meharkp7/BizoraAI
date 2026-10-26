"""Versioned contracts shared by Bizora services."""

from bizora.contracts.comparison import (
    ComparisonVerdict,
    ConfigDifference,
    GraphPair,
    MetricComparison,
    RunComparison,
    SkippedMetric,
)
from bizora.contracts.evidence import EvidenceRef, EvidenceStatus, Provenance
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionResult,
    ExecutionStatus,
    ReportedArtifact,
    ReportedMetric,
    ReproducibilityEcho,
    StructuredError,
)
from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import GraphEdge, GraphNode, MethodologyGraph, NodeKind, validate_graph
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.contracts.run import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    ArtifactRecord,
    CreateExperimentRunRequest,
    ExperimentRun,
    MetricRecord,
    RunState,
    TransitionExperimentRunRequest,
    is_terminal,
    is_valid_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "AdapterExecutionRequest",
    "ArtifactRecord",
    "ComparisonVerdict",
    "ConfigDifference",
    "CreateExperimentRunRequest",
    "EvidenceRef",
    "EvidenceStatus",
    "ExecutionErrorCode",
    "ExecutionLimits",
    "ExecutionResult",
    "ExecutionStatus",
    "ExperimentConfig",
    "ExperimentRun",
    "GraphEdge",
    "GraphNode",
    "GraphPair",
    "GraphPatch",
    "MethodologyGraph",
    "MetricComparison",
    "MetricRecord",
    "NodeKind",
    "PatchOperation",
    "Provenance",
    "ReportedArtifact",
    "ReportedMetric",
    "ReproducibilityEcho",
    "ResultKind",
    "RunComparison",
    "RunState",
    "SkippedMetric",
    "StructuredError",
    "TransitionExperimentRunRequest",
    "is_terminal",
    "is_valid_transition",
    "validate_graph",
]
