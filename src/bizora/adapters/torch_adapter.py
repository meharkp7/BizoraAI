"""Training/eval adapter: fixed seeds, recorded environment, isolated execution.

The adapter compiles the graph with the deep-learning pack's template-only
compiler, pins every seed, records the execution environment, and hands the
validated source to :func:`run_torch_job` — the execution boundary and the
only place torch is ever touched. Fakes in tests stop at that boundary.

Toolchain reality: torch is optional at import time (lazy, never imported
at module top) and Modal credentials are absent, so live training runs are
BLOCKED today. Without torch, :meth:`TorchTrainAdapter.execute` fails
closed with a structured ``blocked`` failure instead of fabricating
results. Full training loops over versioned datasets plus Modal dispatch
are follow-ups; the boundary currently builds the compiled model, fixes
seeds, and runs a synthetic smoke forward pass to prove the artifact runs.
"""

from __future__ import annotations

import importlib
import importlib.util
import platform
import random
import sys
from contextlib import suppress
from dataclasses import dataclass
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
from bizora.packs.deep_learning import (
    GraphCompileError,
    Shape,
    check_first_party_source,
    compile_graph_to_torch,
)

ADAPTER_ID = "bizora.torch-train"
ADAPTER_VERSION = "0.1.0"

MAX_COMPAT_REASONS = 8
MAX_SMOKE_ELEMENTS = 2**20
MAX_SMOKE_DIM = 1024


@dataclass(frozen=True)
class EnvironmentRecord:
    """The recorded execution environment for one run."""

    python_version: str
    platform: str
    torch_version: str | None

    def describe(self) -> str:
        """Render the record as one bounded diagnostics line."""
        torch_label = self.torch_version if self.torch_version else "unavailable"
        return (f"env python {self.python_version} torch {torch_label} on {self.platform}")[:500]


@dataclass(frozen=True)
class TorchJobResult:
    """Outcome of one execution-boundary job (build + smoke forward)."""

    parameter_count: int | None
    smoke_output_shape: tuple[int, ...] | None
    diagnostics: tuple[str, ...]


class TorchJobError(RuntimeError):
    """The execution boundary failed honestly; no results were fabricated."""


class TorchUnavailableError(TorchJobError):
    """The torch toolchain is missing at the execution boundary."""


def torch_module() -> Any | None:
    """Return the torch module, or None when the toolchain is absent.

    Lazy on purpose: importing torch at module top would make the adapter
    unimportable (and untestable) without the heavy toolchain installed.
    """
    if importlib.util.find_spec("torch") is None:
        return None
    try:
        return importlib.import_module("torch")
    except ImportError:
        return None


def torch_version() -> str | None:
    """Return the torch version, or None when the toolchain is absent."""
    module = torch_module()
    if module is None:
        return None
    version = getattr(module, "__version__", None)
    return str(version) if version is not None else "unknown"


def collect_environment() -> EnvironmentRecord:
    """Record the current interpreter, platform, and torch availability."""
    return EnvironmentRecord(
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        torch_version=torch_version(),
    )


def seed_everything(seed: int) -> None:
    """Pin every seed the toolchain offers (stdlib always, torch when present)."""
    random.seed(seed)
    torch = torch_module()
    if torch is None:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    with suppress(Exception):
        torch.use_deterministic_algorithms(True)


def concrete_smoke_shape(entry_shape: Shape | None) -> tuple[int, ...] | None:
    """Return a safe synthetic smoke shape, or None to skip the smoke pass.

    Unknown ranks/dims and absurdly large tensors skip the smoke pass
    instead of guessing or exhausting memory; the skip is reported.
    """
    if entry_shape is None or not entry_shape:
        return None
    concrete: list[int] = []
    elements = 1
    for dim in entry_shape:
        if dim is None or dim < 1 or dim > MAX_SMOKE_DIM:
            return None
        elements *= dim
        if elements > MAX_SMOKE_ELEMENTS:
            return None
        concrete.append(dim)
    return tuple(concrete)


def run_torch_job(
    source: str,
    *,
    module_name: str,
    seed: int,
    entry_shape: tuple[int, ...] | None,
    entry_vocab: int | None,
) -> TorchJobResult:
    """Build the compiled model and run a synthetic smoke forward pass.

    This is the execution boundary: the only function that touches torch.
    Tests fake this function (and only this function). It re-validates the
    source structurally before executing it, so only first-party template
    output can ever run here.
    """
    violations = check_first_party_source(source)
    if violations:
        raise TorchJobError(
            "refusing to execute non-first-party source: " + "; ".join(violations[:4]),
        )
    torch = torch_module()
    if torch is None:
        raise TorchUnavailableError(
            "torch is not installed; live training needs the torch "
            "toolchain on an isolated backend",
        )
    seed_everything(seed)
    namespace: dict[str, Any] = {}
    try:
        # First-party template output only: re-validated above, never model code.
        exec(compile(source, "<bizora-compiled-model>", "exec"), namespace)
    except Exception as exc:
        raise TorchJobError(f"compiled model failed to import: {exc}") from exc
    model_cls = namespace.get(module_name)
    if not isinstance(model_cls, type):
        raise TorchJobError(
            f"compiled source defines no model class {module_name!r}",
        )
    try:
        model = model_cls()
        model.eval()
        parameter_count = sum(int(item.numel()) for item in model.parameters())
    except Exception as exc:
        raise TorchJobError(f"compiled model failed to build: {exc}") from exc
    diagnostics = [f"parameters {parameter_count}"]
    smoke_shape: tuple[int, ...] | None = None
    if entry_shape is None:
        diagnostics.append("smoke forward skipped (unknown entry shape)")
    else:
        try:
            if entry_vocab is not None:
                probe = torch.randint(0, entry_vocab, entry_shape)
            else:
                probe = torch.randn(*entry_shape)
            output = model(probe)
            smoke_shape = tuple(int(dim) for dim in output.shape)
        except Exception as exc:
            raise TorchJobError(f"smoke forward failed: {exc}") from exc
        diagnostics.append(f"smoke output {list(smoke_shape)}")
    return TorchJobResult(
        parameter_count=parameter_count,
        smoke_output_shape=smoke_shape,
        diagnostics=tuple(diagnostics),
    )


class TorchTrainAdapter:
    """Compile, seed, build, and smoke-test graphs behind the adapter interface."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION
    # Executing compiled models needs real isolation (torch, memory-heavy
    # numerical code). The local runner fails closed for this tier, which is
    # exactly the "live training blocked" behavior until Modal lands.
    isolation_requirement = IsolationRequirement.ISOLATED

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
            reasons.append("The torch training adapter never uses network access.")
        if not graph.nodes:
            reasons.append("The torch training adapter requires at least one node.")
        if reasons:
            return tuple(reasons)
        try:
            compile_graph_to_torch(graph)
        except GraphCompileError as exc:
            reasons.extend(exc.errors[:MAX_COMPAT_REASONS])
            if len(exc.errors) > MAX_COMPAT_REASONS:
                remaining = len(exc.errors) - MAX_COMPAT_REASONS
                reasons.append(f"... and {remaining} more compile errors.")
        return tuple(reasons)

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        """Compile, seed, record the environment, and run the boundary job."""
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
        seed = request.config.seed
        seed_everything(seed)
        environment = collect_environment()
        try:
            compiled = compile_graph_to_torch(request.graph)
        except GraphCompileError as exc:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=(f"seed {seed}", environment.describe()),
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=f"graph compilation failed: {'; '.join(exc.errors[:4])}"[:2000],
                ),
            )
        smoke_shape = concrete_smoke_shape(compiled.entry_shape)
        base_diagnostics = (
            f"seed {seed}",
            environment.describe(),
            f"compiled {len(compiled.layers)} layers "
            f"from first-party templates ({', '.join(compiled.template_ids[:8])})",
        )
        try:
            job = run_torch_job(
                compiled.source,
                module_name=compiled.module_name,
                seed=seed,
                entry_shape=smoke_shape,
                entry_vocab=compiled.entry_vocab,
            )
        except TorchUnavailableError as exc:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=base_diagnostics,
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=f"blocked: {exc}"[:2000],
                ),
            )
        except TorchJobError as exc:
            return ExecutionResult(
                run_id=request.run_id,
                status=ExecutionStatus.FAILED,
                echo=self._echo(request),
                diagnostics=base_diagnostics,
                error=StructuredError(
                    code=ExecutionErrorCode.ADAPTER_FAILED,
                    message=str(exc)[:2000],
                ),
            )
        return ExecutionResult(
            run_id=request.run_id,
            status=ExecutionStatus.SUCCEEDED,
            echo=self._echo(request),
            diagnostics=(*base_diagnostics, *job.diagnostics),
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
