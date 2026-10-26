"""Tests for supervised local execution of experiment runs."""

import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.run import ExperimentRun, RunState
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.core.run_service import ExperimentRunService
from bizora.db.base import Base
from bizora.db.models import GraphRevisionRecord
from bizora.db.repository import (
    experiment_run_from_record,
    get_experiment_run,
    get_graph_revision,
    list_artifacts_for_run,
    list_metrics_for_run,
    save_experiment_run,
    save_graph_revision,
)

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


def make_config(**overrides: Any) -> ExperimentConfig:
    """Build a config targeting the deterministic test adapter."""
    payload: dict[str, Any] = {
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


def seed_run(
    session_factory: Callable[[], Session],
    *,
    run_id: str = "run-1",
    config: ExperimentConfig | None = None,
    graph: MethodologyGraph | None = None,
) -> None:
    """Persist a graph revision and a pending run."""
    session = session_factory()
    try:
        revision = graph or make_graph()
        existing = get_graph_revision(
            session,
            project_id=revision.project_id,
            graph_id=revision.graph_id,
            version=revision.version,
        )
        if existing is None:
            save_graph_revision(session, revision)
        save_experiment_run(
            session,
            ExperimentRun(
                run_id=run_id,
                config=config or make_config(),
                state=RunState.PENDING,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
        session.commit()
    finally:
        session.close()


def make_service(
    session_factory: Callable[[], Session],
    *,
    worker_id: str = "worker-a",
    **overrides: Any,
) -> ExecutionService:
    """Build a worker with fast test polling."""
    options: dict[str, Any] = {"poll_seconds": 0.05, "heartbeat_seconds": 60.0}
    options.update(overrides)
    return ExecutionService(
        session_factory,
        WorkerConfig(worker_id=worker_id, **options),
    )


def argv_for(mode: str, *extra: str) -> Callable[[str, str], list[str]]:
    """Build a child command using the fixture adapter script."""

    def build(request_path: str, result_path: str) -> list[str]:
        return [
            sys.executable,
            str(FIXTURE),
            mode,
            request_path,
            result_path,
            *extra,
        ]

    return build


def read_state(
    session_factory: Callable[[], Session], run_id: str
) -> RunState | None:
    """Read one run's state in a fresh session."""
    session = session_factory()
    try:
        record = get_experiment_run(session, run_id)
        return RunState(record.state) if record is not None else None
    finally:
        session.close()


def wait_for_state(
    session_factory: Callable[[], Session],
    run_id: str,
    state: RunState,
    *,
    timeout_seconds: float = 15.0,
) -> None:
    """Wait until a run reaches a state in another thread."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if read_state(session_factory, run_id) == state:
            return
        time.sleep(0.05)
    raise AssertionError(f"Run '{run_id}' never reached '{state.value}'.")


def test_execute_run_succeeds_with_real_runner(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = make_service(session_factory)

    result = service.execute_run("run-1")

    assert result.state == RunState.SUCCEEDED
    assert result.error is None
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.finished_at >= result.started_at


def test_execute_run_fails_unknown_adapter(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory, config=make_config(adapter_id="bizora.unknown"))
    service = make_service(session_factory)

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "adapter_unknown" in result.error
    assert "bizora.unknown" in result.error


def test_execute_run_fails_missing_graph_revision(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory, config=make_config(graph_version=99))
    service = make_service(session_factory)

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "graph_mismatch" in result.error


def test_execute_run_fails_binding_mismatch(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    session = session_factory()
    try:
        revision = session.scalar(select(GraphRevisionRecord).limit(1))
        assert revision is not None
        payload = dict(revision.graph_payload)
        payload["version"] = 99
        revision.graph_payload = payload
        session.commit()
    finally:
        session.close()
    service = make_service(session_factory)

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "graph_mismatch" in result.error


def test_execute_run_fails_incompatible_config(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory, config=make_config(network_access=True))
    service = make_service(session_factory)

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "adapter_incompatible" in result.error


def test_execute_run_missing_run_raises_not_found(
    session_factory: Callable[[], Session],
) -> None:
    service = make_service(session_factory)

    with pytest.raises(BizoraError) as exc_info:
        service.execute_run("missing-run")

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_execute_run_rejects_non_pending_run(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    session = session_factory()
    try:
        ExperimentRunService.transition_run(
            session, "run-1", to_state=RunState.RUNNING
        )
    finally:
        session.close()
    service = make_service(session_factory)

    with pytest.raises(BizoraError) as exc_info:
        service.execute_run("run-1")

    assert exc_info.value.code == ErrorCode.EXPERIMENT_NOT_READY


def test_execute_run_times_out_and_kills_child(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(
            worker_id="worker-a",
            poll_seconds=0.05,
            max_runtime_seconds=2,
            kill_grace_seconds=1,
        ),
        argv_factory=argv_for("slow", "30"),
    )

    started = time.monotonic()
    result = service.execute_run("run-1")
    elapsed = time.monotonic() - started

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "timeout" in result.error
    assert elapsed < 20.0


def test_execute_run_honors_cancellation(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("slow", "30"),
    )
    outcomes: list[RunState] = []

    def run() -> None:
        outcomes.append(service.execute_run("run-1").state)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        wait_for_state(session_factory, "run-1", RunState.RUNNING)
        session = session_factory()
        try:
            ExperimentRunService.transition_run(
                session,
                "run-1",
                to_state=RunState.CANCELLED,
                error="user cancelled",
            )
        finally:
            session.close()
        worker.join(timeout=30.0)
        assert not worker.is_alive()
    finally:
        worker.join(timeout=5.0)

    assert outcomes == [RunState.CANCELLED]
    session = session_factory()
    try:
        record = get_experiment_run(session, "run-1")
        assert record is not None
        assert experiment_run_from_record(record).error == "user cancelled"
    finally:
        session.close()


def test_execute_run_reports_crash_with_exit_code(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("crash", "3"),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "adapter_failed" in result.error
    assert "status 3" in result.error
    assert "fake adapter crashed" in result.error


@pytest.mark.parametrize("mode", ["badjson", "silent"])
def test_execute_run_rejects_unusable_result(
    session_factory: Callable[[], Session], mode: str
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for(mode),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "result_invalid" in result.error


def test_execute_run_rejects_output_overflow(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(
            worker_id="worker-a", poll_seconds=0.05, max_output_bytes=10240
        ),
        argv_factory=argv_for("spam", "1000000"),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "adapter_failed" in result.error


def test_execute_run_enforces_soft_memory_limit(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(
            worker_id="worker-a", poll_seconds=0.05, soft_rss_mb=100
        ),
        argv_factory=argv_for("slow", "30"),
        rss_reader=lambda pid: 999999,
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    assert result.error is not None
    assert "memory_soft_limit" in result.error


def test_execute_run_tolerates_unknown_rss(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("ok"),
        rss_reader=lambda pid: None,
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.SUCCEEDED


def test_child_environment_excludes_secrets(
    session_factory: Callable[[], Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BIZORA_SECRET_KEY", "super-secret")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-secret")
    seed_run(session_factory)
    dump_path = tmp_path / "env.json"
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("env", str(dump_path)),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.SUCCEEDED
    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert {"PATH", "PYTHONPATH", "PYTHONIOENCODING"} <= set(env)
    for key, value in env.items():
        assert "secret" not in f"{key}={value}".lower()


def test_claim_next_available_returns_oldest_pending(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory, run_id="run-old")
    seed_run(session_factory, run_id="run-new")
    service = make_service(session_factory)

    assert service.claim_next_available() == "run-old"
    assert service.claim_next_available() == "run-new"
    assert service.claim_next_available() is None


def test_execute_run_adopts_own_claim(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = make_service(session_factory)

    assert service.claim_next_available() == "run-1"
    result = service.execute_run("run-1")

    assert result.state == RunState.SUCCEEDED


def test_concurrent_execute_runs_single_execution(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def run(worker_id: str) -> None:
        service = make_service(session_factory, worker_id=worker_id)
        barrier.wait(timeout=15.0)
        try:
            final = service.execute_run("run-1")
            outcomes.append(f"ok:{final.state.value}")
        except BizoraError as exc:
            outcomes.append(f"error:{exc.code.value}")

    threads = [
        threading.Thread(target=run, args=("worker-a",)),
        threading.Thread(target=run, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60.0)
    assert not any(thread.is_alive() for thread in threads)

    assert sorted(outcomes)[0].startswith("error:")
    assert outcomes.count("ok:succeeded") == 1
    assert read_state(session_factory, "run-1") == RunState.SUCCEEDED


def test_execute_stops_when_lease_lost(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(
            worker_id="worker-a",
            poll_seconds=0.05,
            heartbeat_seconds=0.1,
        ),
        argv_factory=argv_for("slow", "30"),
    )
    outcomes: list[RunState] = []

    def run() -> None:
        outcomes.append(service.execute_run("run-1").state)

    def steal_lease() -> None:
        time.sleep(0.5)
        session = session_factory()
        try:
            record = get_experiment_run(session, "run-1")
            assert record is not None
            record.worker_id = "worker-b"
            session.commit()
        finally:
            session.close()

    worker = threading.Thread(target=run)
    thief = threading.Thread(target=steal_lease)
    started = time.monotonic()
    worker.start()
    thief.start()
    worker.join(timeout=30.0)
    thief.join(timeout=10.0)
    elapsed = time.monotonic() - started

    assert outcomes == [RunState.RUNNING]
    assert elapsed < 25.0
    session = session_factory()
    try:
        record = get_experiment_run(session, "run-1")
        assert record is not None
        assert record.worker_id == "worker-b"
        assert record.error is None
    finally:
        session.close()


def test_execute_fails_when_run_deleted_mid_run(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("slow", "30"),
    )
    errors: list[str] = []

    def run() -> None:
        try:
            service.execute_run("run-1")
        except BizoraError as exc:
            errors.append(exc.code.value)

    def delete_row() -> None:
        time.sleep(0.5)
        session = session_factory()
        try:
            record = get_experiment_run(session, "run-1")
            assert record is not None
            session.delete(record)
            session.commit()
        finally:
            session.close()

    worker = threading.Thread(target=run)
    deleter = threading.Thread(target=delete_row)
    worker.start()
    deleter.start()
    worker.join(timeout=30.0)
    deleter.join(timeout=10.0)

    assert errors == [ErrorCode.RESOURCE_NOT_FOUND.value]


def test_execute_run_persists_reported_results(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("metrics"),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.SUCCEEDED
    session = session_factory()
    try:
        metrics = list_metrics_for_run(session, "run-1")
        assert [(row.metric_id, row.name, row.value) for row in metrics] == [
            ("metric-accuracy", "accuracy", 0.92)
        ]
        assert metrics[0].result_kind == "measured"
        artifacts = list_artifacts_for_run(session, "run-1")
        assert [
            (row.artifact_id, row.kind, row.uri) for row in artifacts
        ] == [
            (
                "artifact-checkpoint",
                "checkpoint",
                "file:///tmp/fake-checkpoint",
            )
        ]
        assert artifacts[0].sha256 == "b" * 64
    finally:
        session.close()


def test_execute_run_discards_failed_run_results(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(session_factory)
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        argv_factory=argv_for("failedmetrics"),
    )

    result = service.execute_run("run-1")

    assert result.state == RunState.FAILED
    session = session_factory()
    try:
        assert list_metrics_for_run(session, "run-1") == []
        assert list_artifacts_for_run(session, "run-1") == []
    finally:
        session.close()


@pytest.mark.parametrize(
    "options",
    [
        {"worker_id": ""},
        {"worker_id": "w", "lease_ttl_seconds": 0},
        {"worker_id": "w", "heartbeat_seconds": 0.0},
        {"worker_id": "w", "poll_seconds": 0.0},
        {"worker_id": "w", "max_runtime_seconds": 0},
        {"worker_id": "w", "max_runtime_seconds": 86_401},
        {"worker_id": "w", "soft_rss_mb": 0},
        {"worker_id": "w", "max_output_bytes": 1023},
        {"worker_id": "w", "kill_grace_seconds": -1},
    ],
)
def test_worker_config_rejects_invalid_tuning(options: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        WorkerConfig(**options)
