"""ngspice execution adapter behind the shared adapter interface.

The adapter extracts a SPICE netlist from the run graph (see
:mod:`bizora.packs.electronics.netlist`), executes it with a real local
ngspice binary in batch mode, and reports every parsed measurement as a
``measured`` metric. Analysis directives (``.op``/``.tran``/control
blocks/``.meas``) arrive as graph data, never as adapter branches.
"""

from __future__ import annotations

import math

from bizora.adapters.isolation import IsolationRequirement
from bizora.adapters.ngspice_runner import resolve_ngspice, run_netlist
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionResult,
    ExecutionStatus,
    ReportedMetric,
    ReproducibilityEcho,
    StructuredError,
)
from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import MethodologyGraph
from bizora.packs.electronics.netlist import extract_netlist, simulatable_nodes

ADAPTER_ID = "bizora.ngspice"
ADAPTER_VERSION = "0.1.0"

MAX_DIAGNOSTICS = 32
MAX_METRICS = 100


class NgspiceAdapter:
    """Execute methodology-graph circuits with local ngspice batch runs."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION
    # Local-only subprocess of a real binary: no network, temp-dir-only
    # writes, caller-supplied timeout and output caps. Same-user execution
    # like the runner itself, so local-trusted, never a sandbox claim.
    isolation_requirement = IsolationRequirement.LOCAL_TRUSTED

    def check_compatibility(
        self,
        config: ExperimentConfig,
        graph: MethodologyGraph,
    ) -> tuple[str, ...]:
        """Return reasons this adapter cannot accept the run."""
        reasons: list[str] = []
        if config.adapter_id != self.adapter_id:
            reasons.append(f"Adapter id '{config.adapter_id}' does not match '{self.adapter_id}'.")
        if config.adapter_version != self.adapter_version:
            reasons.append(
                f"Adapter version '{config.adapter_version}' does not match "
                f"'{self.adapter_version}'."
            )
        if config.network_access:
            reasons.append("The ngspice adapter never uses network access.")
        if not simulatable_nodes(graph):
            reasons.append(
                "The ngspice adapter requires at least one node with a "
                "simulatable 'spice_kind' config value."
            )
        if resolve_ngspice() is None:
            reasons.append("No ngspice binary found on PATH or at the known location.")
        return tuple(reasons)

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        """Run the graph circuit and return measured metrics without raising."""
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
        executable = resolve_ngspice()
        assert executable is not None  # guaranteed by check_compatibility
        try:
            netlist = extract_netlist(request.graph)
            run = run_netlist(
                netlist.text,
                executable=executable,
                timeout_seconds=request.limits.timeout_seconds,
                max_output_bytes=request.limits.max_output_bytes,
            )
        except Exception as exc:  # domain failure, never a raise
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=("ngspice invocation failed",),
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=f"ngspice invocation failed: {exc}"[:2000],
                ),
            )

        diagnostics: list[str] = [
            f"simulated {len(netlist.element_lines)} elements, "
            f"{len(netlist.directive_lines)} directives",
        ]
        diagnostics.extend(f"extract: {warning}"[:2000] for warning in netlist.warnings)
        diagnostics.extend(f"ngspice: {error}"[:2000] for error in run.errors)
        for name in run.failed_measurements:
            diagnostics.append(f"measurement '{name}' reported as failed"[:2000])
        if run.truncated:
            diagnostics.append("ngspice output truncated at max_output_bytes")

        if run.timed_out:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
                error=StructuredError(
                    code=ExecutionErrorCode.TIMEOUT,
                    message=(
                        f"ngspice exceeded {request.limits.timeout_seconds}s wall-clock limit."
                    ),
                ),
            )
        if run.returncode != 0:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=(f"ngspice exited with code {run.returncode}.")[:2000],
                    exit_code=run.returncode,
                ),
            )

        metrics: list[ReportedMetric] = []
        for measurement in run.measurements:
            if len(metrics) >= MAX_METRICS:
                diagnostics.append("metric cap reached; further measurements dropped")
                break
            if not math.isfinite(measurement.value):
                diagnostics.append(
                    f"measurement '{measurement.name}' is non-finite; dropped"[:2000]
                )
                continue
            metrics.append(
                ReportedMetric(
                    metric_id=measurement.name[:128],
                    name=measurement.name[:128],
                    value=measurement.value,
                    result_kind=ResultKind.MEASURED,
                )
            )
        if not metrics:
            diagnostics.append(
                "no measurements parsed; add print or .meas directives as graph data"
            )
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=(
                        "ngspice ran but produced no measurements; the graph "
                        "needs print or .meas directives."
                    ),
                ),
            )
        diagnostics.append(f"measured {len(metrics)} metrics with ngspice")
        return ExecutionResult(
            run_id=request.run_id,
            status=ExecutionStatus.SUCCEEDED,
            echo=self._echo(request),
            diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
            metrics=tuple(metrics),
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
