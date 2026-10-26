"""Tests for the deterministic test adapter."""

from bizora.adapters.deterministic_test import DeterministicTestAdapter
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


def make_config(**overrides: object) -> ExperimentConfig:
    """Build a config targeting the deterministic test adapter."""
    payload: dict[str, object] = {
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
        "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 0,
    }
    payload.update(overrides)
    return ExperimentConfig.model_validate(payload)


def make_graph() -> MethodologyGraph:
    """Build a minimal methodology graph."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Vision Transformer",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(
            GraphEdge(id="edge-1", source="input", target="encoder"),
            GraphEdge(id="edge-2", source="encoder", target="output"),
        ),
        created_by="researcher-1",
    )


def make_request(
    config: ExperimentConfig | None = None,
    graph: MethodologyGraph | None = None,
) -> AdapterExecutionRequest:
    """Build an execution request for the test adapter."""
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


def test_adapter_identity_is_stable() -> None:
    adapter = DeterministicTestAdapter()

    assert adapter.adapter_id == "bizora.deterministic-test"
    assert adapter.adapter_version == "0.1.0"


def test_compatibility_accepts_matching_config() -> None:
    adapter = DeterministicTestAdapter()

    assert adapter.check_compatibility(make_config(), make_graph()) == ()


def test_compatibility_rejects_wrong_adapter_id() -> None:
    adapter = DeterministicTestAdapter()
    config = make_config(adapter_id="other.adapter")

    reasons = adapter.check_compatibility(config, make_graph())

    assert len(reasons) == 1
    assert "other.adapter" in reasons[0]


def test_compatibility_rejects_wrong_adapter_version() -> None:
    adapter = DeterministicTestAdapter()
    config = make_config(adapter_version="9.9.9")

    reasons = adapter.check_compatibility(config, make_graph())

    assert len(reasons) == 1
    assert "9.9.9" in reasons[0]


def test_compatibility_rejects_network_access() -> None:
    adapter = DeterministicTestAdapter()
    config = make_config(network_access=True)

    reasons = adapter.check_compatibility(config, make_graph())

    assert len(reasons) == 1
    assert "network" in reasons[0]


def test_compatibility_rejects_empty_graph() -> None:
    adapter = DeterministicTestAdapter()
    graph = make_graph().model_copy(update={"nodes": ()})

    reasons = adapter.check_compatibility(make_config(), graph)

    assert len(reasons) == 1
    assert "at least one node" in reasons[0]


def test_execute_succeeds_and_echoes_reproducibility() -> None:
    adapter = DeterministicTestAdapter()

    result = adapter.execute(make_request())

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.run_id == "run-1"
    assert result.error is None
    assert result.echo.seed == 42
    assert result.echo.dataset_revision == "sha256:example"
    assert result.echo.code_revision == "abcdef1"
    assert result.echo.graph_version == 1
    assert result.diagnostics != ()
    assert result.metrics == ()
    assert result.artifacts == ()


def test_execute_is_deterministic() -> None:
    adapter = DeterministicTestAdapter()

    first = adapter.execute(make_request())
    second = adapter.execute(make_request())

    assert first == second


def test_execute_returns_failed_result_for_incompatible_config() -> None:
    adapter = DeterministicTestAdapter()
    request = make_request(config=make_config(adapter_version="9.9.9"))

    result = adapter.execute(request)

    assert result.status == ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == ExecutionErrorCode.ADAPTER_INCOMPATIBLE
    assert "9.9.9" in result.error.message
