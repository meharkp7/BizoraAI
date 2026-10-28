"""Tests for execution-service telemetry publishing and router mounting."""

import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.run import ExperimentRun, RunState
from bizora.contracts.streaming import TelemetryEventKind
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.db.base import Base
from bizora.db.repository import save_experiment_run, save_graph_revision
from bizora.main import app
from bizora.streaming.bus import TelemetryBus, get_shared_bus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "fake_adapter_child.py"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Create an isolated file database for each test."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/worker.db", connect_args={"timeout": 30}
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a factory for short-lived sessions."""
    return lambda: Session(engine)


def _make_config() -> ExperimentConfig:
    """Build a config targeting the deterministic test adapter."""
    return ExperimentConfig.model_validate(
        {
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
    )


def _make_graph() -> MethodologyGraph:
    """Build a minimal methodology graph."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Vision Transformer",
        source_ids=("paper-1",),
        created_by="researcher-1",
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="encoder", kind=NodeKind.MODEL, label="Encoder"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(
            GraphEdge(id="edge-1", source="input", target="encoder"),
            GraphEdge(id="edge-2", source="encoder", target="output"),
        ),
    )


def _seed_run(session_factory: Callable[[], Session], run_id: str) -> None:
    """Persist a graph revision and a pending run."""
    session = session_factory()
    try:
        save_graph_revision(session, _make_graph())
        save_experiment_run(
            session,
            ExperimentRun(
                run_id=run_id,
                config=_make_config(),
                state=RunState.PENDING,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
        session.commit()
    finally:
        session.close()


def _argv_for(mode: str, *extra: str) -> Callable[[str, str], list[str]]:
    """Build a child command using the fixture adapter script."""

    def build(request_path: str, result_path: str) -> list[str]:
        return [sys.executable, str(FIXTURE), mode, request_path, result_path, *extra]

    return build


def _make_service(
    session_factory: Callable[[], Session],
    bus: TelemetryBus,
    mode: str,
    *extra: str,
) -> ExecutionService:
    """Build a worker with fast test polling and a telemetry bus."""
    return ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-telemetry", poll_seconds=0.05, heartbeat_seconds=60.0),
        argv_factory=_argv_for(mode, *extra),
        telemetry_bus=bus,
    )


def test_success_publishes_running_metric_and_terminal(
    session_factory: Callable[[], Session],
) -> None:
    """A succeeded run streams claim, metrics, and a closing terminal event."""
    _seed_run(session_factory, "run-telemetry-ok")
    bus = TelemetryBus()
    service = _make_service(session_factory, bus, "metrics")

    run = service.execute_run("run-telemetry-ok")

    assert run.state == RunState.SUCCEEDED
    events = bus.replay("run-telemetry-ok")
    assert [event.seq for event in events] == [0, 1, 2]
    assert [event.kind for event in events] == [
        TelemetryEventKind.STATE,
        TelemetryEventKind.METRIC,
        TelemetryEventKind.STATE,
    ]
    assert events[0].state is not None and events[0].state.state == RunState.RUNNING
    assert events[1].metric is not None
    assert events[1].metric.name == "accuracy"
    assert events[1].metric.value == 0.92
    assert events[2].state is not None and events[2].state.state == RunState.SUCCEEDED
    assert bus.is_closed("run-telemetry-ok") is True


def test_failure_publishes_running_then_failed_terminal(
    session_factory: Callable[[], Session],
) -> None:
    """A crashed run streams its claim and a closing failed event."""
    _seed_run(session_factory, "run-telemetry-crash")
    bus = TelemetryBus()
    service = _make_service(session_factory, bus, "crash", "3")

    run = service.execute_run("run-telemetry-crash")

    assert run.state == RunState.FAILED
    events = bus.replay("run-telemetry-crash")
    assert [event.kind for event in events] == [
        TelemetryEventKind.STATE,
        TelemetryEventKind.STATE,
    ]
    assert events[0].state is not None and events[0].state.state == RunState.RUNNING
    assert events[1].state is not None and events[1].state.state == RunState.FAILED
    assert events[1].state.error
    assert bus.is_closed("run-telemetry-crash") is True


def test_shared_bus_is_process_singleton() -> None:
    """The worker and the router observe the same bus instance."""
    assert get_shared_bus() is get_shared_bus()


def test_streaming_routes_are_mounted_on_app() -> None:
    """The assembled app serves the telemetry stream and replay endpoints."""
    paths = set(app.openapi()["paths"])
    assert "/api/v1/experiments/runs/{run_id}/telemetry/stream" in paths
    assert "/api/v1/experiments/runs/{run_id}/telemetry/events" in paths
