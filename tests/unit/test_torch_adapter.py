"""Tests for the torch training/eval adapter (torch itself is faked or absent)."""

import random
from typing import Any

import pytest

from bizora.adapters import torch_adapter
from bizora.adapters.base import ExecutionAdapter
from bizora.adapters.isolation import IsolationRequirement
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionStatus,
)
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.packs import deep_learning


def make_config(**overrides: object) -> ExperimentConfig:
    """Build a config targeting the torch training adapter."""
    payload: dict[str, object] = {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "bizora.torch-train",
        "adapter_version": "0.1.0",
        "dataset_id": "demo-tensors",
        "dataset_revision": "rev-1",
        "seed": 7,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 0,
    }
    payload.update(overrides)
    return ExperimentConfig.model_validate(payload)


def make_graph() -> MethodologyGraph:
    """Build a compilable graph: input(2,8) -> linear 8->4 -> output."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Stack",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                label="Input",
                output_shape=(2, 8),
            ),
            GraphNode(
                id="dense",
                kind=NodeKind.MODEL,
                label="Dense",
                config={"layer": "linear", "in_features": 8, "out_features": 4},
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Output"),
        ),
        edges=(
            GraphEdge(id="e1", source="input", target="dense"),
            GraphEdge(id="e2", source="dense", target="output"),
        ),
        created_by="tester",
    )


def make_request(
    config: ExperimentConfig | None = None,
    graph: MethodologyGraph | None = None,
) -> AdapterExecutionRequest:
    """Build an execution request for the torch adapter."""
    return AdapterExecutionRequest(
        run_id="run-1",
        config=config or make_config(),
        graph=graph or make_graph(),
        limits=ExecutionLimits(
            timeout_seconds=600,
            cpu_seconds=600,
            soft_rss_mb=512,
            max_output_bytes=1_000_000,
            kill_grace_seconds=10,
        ),
    )


def test_adapter_identity_and_interface() -> None:
    """The adapter quacks as an ExecutionAdapter with pinned id/version."""
    adapter = torch_adapter.TorchTrainAdapter()
    assert isinstance(adapter, ExecutionAdapter)
    assert adapter.adapter_id == "bizora.torch-train"
    assert adapter.adapter_version == "0.1.0"
    assert torch_adapter.ADAPTER_ID == "bizora.torch-train"
    assert torch_adapter.ADAPTER_VERSION == "0.1.0"
    assert adapter.isolation_requirement is IsolationRequirement.ISOLATED


def test_adapter_id_matches_pack_wiring() -> None:
    """Adapter id constant matches; pack reports none until execution exists."""
    assert torch_adapter.ADAPTER_ID == deep_learning.TORCH_ADAPTER_ID
    assert deep_learning.pack.simulator_adapter_ids == ()


def test_check_compatibility_accepts_compilable_graph() -> None:
    """A matching config plus a compilable graph yields no reasons."""
    adapter = torch_adapter.TorchTrainAdapter()
    assert adapter.check_compatibility(make_config(), make_graph()) == ()


def test_check_compatibility_rejects_mismatches() -> None:
    """Identity, network, empty-graph, and compile problems all surface."""
    adapter = torch_adapter.TorchTrainAdapter()
    assert (
        adapter.check_compatibility(
            make_config(adapter_id="other"),
            make_graph(),
        )
        != ()
    )
    assert (
        adapter.check_compatibility(
            make_config(adapter_version="9.9.9"),
            make_graph(),
        )
        != ()
    )
    assert (
        adapter.check_compatibility(
            make_config(network_access=True),
            make_graph(),
        )
        != ()
    )
    empty = make_graph().model_copy(update={"nodes": ()})
    assert adapter.check_compatibility(make_config(), empty) != ()
    broken = make_graph().model_copy(
        update={
            "nodes": (
                GraphNode(
                    id="only",
                    kind=NodeKind.MODEL,
                    label="Only",
                    config={"layer": "fancy-new-op"},
                ),
            )
        }
    )
    reasons = adapter.check_compatibility(make_config(), broken)
    assert any("unknown layer" in reason for reason in reasons)


def test_execute_rejects_incompatible_requests() -> None:
    """Incompatible requests fail structured, with a reproducibility echo."""
    adapter = torch_adapter.TorchTrainAdapter()
    result = adapter.execute(make_request(config=make_config(adapter_id="other")))
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.ADAPTER_INCOMPATIBLE
    assert result.run_id == "run-1"
    assert result.echo.adapter_id == "other"
    assert result.echo.seed == 7


def test_execute_is_blocked_without_torch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the toolchain, execute fails closed as blocked (never fakes)."""
    monkeypatch.setattr(torch_adapter, "torch_module", lambda: None)
    adapter = torch_adapter.TorchTrainAdapter()
    result = adapter.execute(make_request())
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.ADAPTER_FAILED
    assert result.error.message.startswith("blocked: torch is not installed")
    assert result.diagnostics[0] == "seed 7"
    assert "torch unavailable" in result.diagnostics[1]
    assert "compiled 1 layers from first-party templates" in result.diagnostics[2]
    assert result.echo.seed == 7
    assert result.echo.graph_id == "graph-1"


def test_execute_succeeds_with_boundary_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fakes stop at the execution boundary: seed, env, and job all record."""
    seen: dict[str, Any] = {}

    def fake_run_torch_job(
        source: str,
        *,
        module_name: str,
        seed: int,
        entry_shape: tuple[int, ...] | None,
        entry_vocab: int | None,
    ) -> torch_adapter.TorchJobResult:
        seen["source"] = source
        seen["module_name"] = module_name
        seen["seed"] = seed
        seen["entry_shape"] = entry_shape
        seen["entry_vocab"] = entry_vocab
        return torch_adapter.TorchJobResult(
            parameter_count=36,
            smoke_output_shape=(2, 4),
            diagnostics=("parameters 36", "smoke output [2, 4]"),
        )

    monkeypatch.setattr(torch_adapter, "run_torch_job", fake_run_torch_job)
    adapter = torch_adapter.TorchTrainAdapter()
    result = adapter.execute(make_request())
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.error is None
    assert result.echo.adapter_id == "bizora.torch-train"
    assert result.echo.adapter_version == "0.1.0"
    assert result.echo.seed == 7
    assert result.echo.dataset_id == "demo-tensors"
    assert result.diagnostics[0] == "seed 7"
    assert result.diagnostics[1].startswith("env python ")
    assert "first-party templates" in result.diagnostics[2]
    assert "parameters 36" in result.diagnostics
    assert "smoke output [2, 4]" in result.diagnostics
    assert seen["seed"] == 7
    assert seen["module_name"] == "DeepLearningModel"
    assert seen["entry_shape"] == (2, 8)
    assert seen["entry_vocab"] is None
    assert "nn.Linear(8, 4" in seen["source"]


def test_execute_maps_boundary_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Honest boundary failures surface as structured adapter failures."""

    def fake_run_torch_job(*args: object, **kwargs: object) -> Any:
        raise torch_adapter.TorchJobError("smoke forward failed: boom")

    monkeypatch.setattr(torch_adapter, "run_torch_job", fake_run_torch_job)
    adapter = torch_adapter.TorchTrainAdapter()
    result = adapter.execute(make_request())
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.ADAPTER_FAILED
    assert "smoke forward failed" in result.error.message


def test_boundary_refuses_foreign_source() -> None:
    """The boundary re-validates source before executing anything."""
    with pytest.raises(torch_adapter.TorchJobError, match="non-first-party"):
        torch_adapter.run_torch_job(
            "import os\n",
            module_name="DeepLearningModel",
            seed=7,
            entry_shape=(2, 8),
            entry_vocab=None,
        )


def test_boundary_reports_missing_toolchain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean source plus no torch raises the unavailable error (no fake run)."""
    monkeypatch.setattr(torch_adapter, "torch_module", lambda: None)
    compiled = deep_learning.compile_graph_to_torch(make_graph())
    with pytest.raises(torch_adapter.TorchUnavailableError, match="not installed"):
        torch_adapter.run_torch_job(
            compiled.source,
            module_name=compiled.module_name,
            seed=7,
            entry_shape=(2, 8),
            entry_vocab=None,
        )


def test_seed_everything_is_deterministic() -> None:
    """Fixed seeds reproduce the stdlib stream (torch adds its own)."""
    torch_adapter.seed_everything(1234)
    first = [random.random() for _ in range(3)]
    torch_adapter.seed_everything(1234)
    second = [random.random() for _ in range(3)]
    assert first == second
    torch_adapter.seed_everything(999)
    assert [random.random() for _ in range(3)] != first


def test_concrete_smoke_shape_guards() -> None:
    """Unknown, empty, non-positive, and huge shapes skip the smoke pass."""
    assert torch_adapter.concrete_smoke_shape(None) is None
    assert torch_adapter.concrete_smoke_shape(()) is None
    assert torch_adapter.concrete_smoke_shape((2, 8)) == (2, 8)
    assert torch_adapter.concrete_smoke_shape((2, None)) is None
    assert torch_adapter.concrete_smoke_shape((0, 8)) is None
    assert torch_adapter.concrete_smoke_shape((2048, 8)) is None
    assert torch_adapter.concrete_smoke_shape((64, 64, 64)) == (64, 64, 64)
    assert torch_adapter.concrete_smoke_shape((128, 128, 128)) is None


def test_collect_environment_records_reality() -> None:
    """The environment record always names interpreter, platform, torch."""
    environment = torch_adapter.collect_environment()
    assert environment.python_version
    assert environment.platform
    assert "python" in environment.describe()
    assert "torch" in environment.describe()
