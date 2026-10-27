"""Tests for automatic expired-lease recovery by workers.

Recovery is worker-driven: claiming or executing reaps expired leases
first, so a crashed worker's runs become terminal failed runs instead of
hanging in running forever. Reaped runs are never retried.
"""

import json
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
from bizora.core.errors import BizoraError
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.db.base import Base
from bizora.db.models import ExperimentRunRecord
from bizora.db.repository import (
    claim_experiment_run,
    get_experiment_run,
    get_graph_revision,
    list_metrics_for_run,
    save_experiment_run,
    save_graph_revision,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "fake_adapter_child.py"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Create an isolated file database for each test."""
    engine = create_engine(f"sqlite:///{tmp_path}/leases.db", connect_args={"timeout": 30})
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
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(GraphEdge(id="edge-1", source="input", target="output"),),
        created_by="researcher-1",
    )


def seed_pending(
    session_factory: Callable[[], Session],
    run_id: str,
    now: datetime | None = None,
) -> None:
    """Persist the graph revision and one pending run."""
    session = session_factory()
    try:
        graph = make_graph()
        if (
            get_graph_revision(
                session,
                project_id=graph.project_id,
                graph_id=graph.graph_id,
                version=graph.version,
            )
            is None
        ):
            save_graph_revision(session, graph)
        save_experiment_run(
            session,
            ExperimentRun(
                run_id=run_id,
                config=make_config(),
                state=RunState.PENDING,
                created_at=now or datetime.now(UTC),
            ),
        )
        session.commit()
    finally:
        session.close()


def claim_with_lease(
    session_factory: Callable[[], Session],
    run_id: str,
    worker_id: str,
    *,
    claimed_at: datetime,
    ttl_seconds: int = 300,
) -> None:
    """Claim a run with an explicit claim time."""
    session = session_factory()
    try:
        claimed = claim_experiment_run(
            session,
            run_id=run_id,
            worker_id=worker_id,
            now=claimed_at,
            lease_ttl_seconds=ttl_seconds,
        )
        assert claimed is not None
        session.commit()
    finally:
        session.close()


def read_record(session_factory: Callable[[], Session], run_id: str) -> ExperimentRunRecord:
    """Return a fresh copy of one run record."""
    session = session_factory()
    try:
        record = get_experiment_run(session, run_id)
        assert record is not None
        session.expunge(record)
        return record
    finally:
        session.close()


def error_code(record: ExperimentRunRecord) -> str | None:
    """Return the structured error code recorded for a run."""
    if record.error is None:
        return None
    return str(json.loads(record.error)["code"])


def make_service(
    session_factory: Callable[[], Session],
    worker_id: str = "worker-a",
    **tuning: Any,
) -> ExecutionService:
    """Build a worker with fast polling for tests."""
    options: dict[str, Any] = {"poll_seconds": 0.05, "heartbeat_seconds": 60.0}
    options.update(tuning)
    return ExecutionService(session_factory, WorkerConfig(worker_id=worker_id, **options))


def argv_for(mode: str, *extra: str) -> Callable[[str, str], list[str]]:
    """Build an argv factory for the synthetic adapter child."""
    return lambda request, result: [
        sys.executable,
        str(FIXTURE),
        mode,
        request,
        result,
        *extra,
    ]


def test_claim_reaps_expired_lease_first(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-stale")
    seed_pending(session_factory, "run-fresh")
    claim_with_lease(
        session_factory,
        "run-stale",
        "dead-worker",
        claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )

    claimed = make_service(session_factory).claim_next_available()

    assert claimed == "run-fresh"
    stale = read_record(session_factory, "run-stale")
    assert stale.state == RunState.FAILED.value
    assert error_code(stale) == "lease_expired"


def test_execute_run_reaps_expired_leases_first(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-stale")
    seed_pending(session_factory, "run-live")
    claim_with_lease(
        session_factory,
        "run-stale",
        "dead-worker",
        claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )

    final = make_service(session_factory).execute_run("run-live")

    assert final.state == RunState.SUCCEEDED
    stale = read_record(session_factory, "run-stale")
    assert stale.state == RunState.FAILED.value
    assert error_code(stale) == "lease_expired"


def test_recover_is_idempotent(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-stale")
    claim_with_lease(
        session_factory,
        "run-stale",
        "dead-worker",
        claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    service = make_service(session_factory)

    assert service.recover_expired_leases() == 1
    assert service.recover_expired_leases() == 0

    stale = read_record(session_factory, "run-stale")
    assert stale.state == RunState.FAILED.value
    assert error_code(stale) == "lease_expired"


def test_recover_ignores_active_worker(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-live")
    claim_with_lease(
        session_factory,
        "run-live",
        "worker-a",
        claimed_at=datetime.now(UTC),
        ttl_seconds=3600,
    )

    assert make_service(session_factory).recover_expired_leases() == 0

    live = read_record(session_factory, "run-live")
    assert live.state == RunState.RUNNING.value
    assert live.error is None


def test_concurrent_reapers_reap_exactly_once(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-stale")
    claim_with_lease(
        session_factory,
        "run-stale",
        "dead-worker",
        claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    barrier = threading.Barrier(2)
    counts: list[int] = []

    def reap(worker_id: str) -> None:
        barrier.wait(timeout=15.0)
        counts.append(make_service(session_factory, worker_id).recover_expired_leases())

    threads = [
        threading.Thread(target=reap, args=("worker-a",)),
        threading.Thread(target=reap, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30.0)
    assert not any(thread.is_alive() for thread in threads)

    assert sorted(counts) == [0, 1]
    stale = read_record(session_factory, "run-stale")
    assert stale.state == RunState.FAILED.value
    assert error_code(stale) == "lease_expired"


def test_stale_worker_cannot_finalize_after_reap(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-1")
    claim_with_lease(
        session_factory,
        "run-1",
        "worker-a",
        claimed_at=datetime.now(UTC),
        ttl_seconds=3600,
    )
    worker = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05, heartbeat_seconds=60.0),
        argv_factory=argv_for("slow", "30"),
    )
    outcomes: list[RunState] = []

    def run() -> None:
        outcomes.append(worker.execute_run("run-1").state)

    def expire_and_reap() -> None:
        time.sleep(0.5)
        session = session_factory()
        try:
            record = get_experiment_run(session, "run-1")
            assert record is not None
            record.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        finally:
            session.close()
        reaped = make_service(session_factory, "worker-b")
        assert reaped.recover_expired_leases() == 1

    supervising = threading.Thread(target=run)
    reaper = threading.Thread(target=expire_and_reap)
    started = time.monotonic()
    supervising.start()
    reaper.start()
    supervising.join(timeout=30.0)
    reaper.join(timeout=10.0)
    elapsed = time.monotonic() - started

    assert outcomes == [RunState.FAILED]
    assert elapsed < 25.0
    record = read_record(session_factory, "run-1")
    assert error_code(record) == "lease_expired"
    session = session_factory()
    try:
        assert list_metrics_for_run(session, "run-1") == []
    finally:
        session.close()


def test_reaped_run_is_never_retried(
    session_factory: Callable[[], Session],
) -> None:
    seed_pending(session_factory, "run-stale")
    claim_with_lease(
        session_factory,
        "run-stale",
        "dead-worker",
        claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    service = make_service(session_factory)
    assert service.recover_expired_leases() == 1

    with pytest.raises(BizoraError):
        service.execute_run("run-stale")

    assert service.claim_next_available() is None
    stale = read_record(session_factory, "run-stale")
    assert stale.state == RunState.FAILED.value
