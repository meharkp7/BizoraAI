"""Deterministic test adapter for execution-boundary integration tests."""

import hashlib
import json
from typing import Any

from bizora.adapters.isolation import IsolationRequirement
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    ReproducibilityEcho,
    StructuredError,
)
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import MethodologyGraph


def _canonical_json(payload: dict[str, Any]) -> str:
    """Return a deterministic JSON encoding of a payload."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class DeterministicTestAdapter:
    """Validate inputs and echo reproducibility fields without external effects."""

    adapter_id = "bizora.deterministic-test"
    adapter_version = "0.1.0"
    # First-party pure validation and hashing: no network, no subprocess,
    # no filesystem writes. Safe for local-trusted execution.
    isolation_requirement = IsolationRequirement.LOCAL_TRUSTED

    def check_compatibility(
        self,
        config: ExperimentConfig,
        graph: MethodologyGraph,
    ) -> tuple[str, ...]:
        """Return reasons this adapter cannot accept the run."""
        reasons: list[str] = []
        if config.adapter_id != self.adapter_id:
            reasons.append(
                f"Adapter id '{config.adapter_id}' does not match "
                f"'{self.adapter_id}'."
            )
        if config.adapter_version != self.adapter_version:
            reasons.append(
                f"Adapter version '{config.adapter_version}' does not match "
                f"'{self.adapter_version}'."
            )
        if config.network_access:
            reasons.append("The deterministic test adapter never uses network access.")
        if not graph.nodes:
            reasons.append("The deterministic test adapter requires at least one node.")
        return tuple(reasons)

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        """Validate the request and return a deterministic outcome."""
        reasons = self.check_compatibility(request.config, request.graph)
        if reasons:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=("compatibility check failed",),
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_INCOMPATIBLE,
                    message="; ".join(reasons)[:2000],
                ),
            )

        checksum = hashlib.sha256(
            _canonical_json(
                {
                    "config": request.config.model_dump(mode="json"),
                    "graph": request.graph.model_dump(mode="json"),
                }
            ).encode("utf-8")
        ).hexdigest()

        node_count = len(request.graph.nodes)
        edge_count = len(request.graph.edges)
        return ExecutionResult(
            run_id=request.run_id,
            status=ExecutionStatus.SUCCEEDED,
            echo=self._echo(request),
            diagnostics=(
                f"validated {node_count} nodes, {edge_count} edges",
                f"input checksum {checksum[:16]}",
                f"seed {request.config.seed}",
            ),
        )

    def _echo(self, request: AdapterExecutionRequest) -> ReproducibilityEcho:
        """Echo the request's reproducibility fields for runner verification."""
        config = request.config
        return ReproducibilityEcho(
            adapter_id=config.adapter_id,
            adapter_version=config.adapter_version,
            dataset_id=config.dataset_id,
            dataset_revision=config.dataset_revision,
            code_revision=config.code_revision,
            seed=config.seed,
            graph_id=config.graph_id,
            graph_version=config.graph_version,
        )
