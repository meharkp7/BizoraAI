"""API tests for the experiment run lifecycle."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.contracts.experiment import ResultKind
from bizora.contracts.run import ArtifactRecord, MetricRecord
from bizora.db.base import Base
from bizora.db.repository import save_artifact_record, save_metric_record
from bizora.db.session import get_db_session
from bizora.main import app


def make_graph_payload() -> dict[str, object]:
    """Build a minimal graph request payload."""
    return {
        "project_id": "project-api",
        "graph_id": "graph-api",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-api"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
            {"id": "output", "kind": "output", "label": "Predictions"},
        ],
        "edges": [
            {"id": "edge-1", "source": "input", "target": "encoder"},
            {"id": "edge-2", "source": "encoder", "target": "output"},
        ],
        "created_by": "api-test",
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide a test client backed by an isolated SQLite database."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        engine.dispose()


def make_config_payload(
    *,
    project_id: str = "project-api",
    graph_id: str = "graph-api",
    graph_version: int = 1,
) -> dict[str, Any]:
    """Build a config payload referencing the API test graph."""
    return {
        "experiment_id": "exp-api-1",
        "project_id": project_id,
        "graph_id": graph_id,
        "graph_version": graph_version,
        "adapter_id": "hf-vit-classification",
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
        "max_gpu_count": 1,
    }


def create_run(
    client: TestClient,
    *,
    run_id: str = "run-api-1",
    config: dict[str, Any] | None = None,
) -> Any:
    """Create a run through the API."""
    return client.post(
        "/api/v1/experiments/runs",
        json={
            "run_id": run_id,
            "config": config or make_config_payload(),
        },
    )


def test_create_and_retrieve_run(client: TestClient) -> None:
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201

    created = create_run(client)

    assert created.status_code == 201
    body = created.json()
    assert body["run_id"] == "run-api-1"
    assert body["state"] == "pending"
    assert body["config"]["experiment_id"] == "exp-api-1"
    assert body["config"]["graph_version"] == 1
    assert body["started_at"] is None
    assert body["finished_at"] is None

    retrieved = client.get("/api/v1/experiments/runs/run-api-1")
    assert retrieved.status_code == 200
    assert retrieved.json() == body


def test_create_run_rejects_missing_graph_revision(
    client: TestClient,
) -> None:
    response = create_run(client)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_create_run_rejects_duplicate_run_id(client: TestClient) -> None:
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201

    first = create_run(client)
    duplicate = create_run(client)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_get_missing_run_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/experiments/runs/missing-run")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_transition_run_through_lifecycle(client: TestClient) -> None:
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201
    created = create_run(client)
    assert created.status_code == 201

    running = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "running"},
    )
    assert running.status_code == 200
    assert running.json()["state"] == "running"
    assert running.json()["started_at"] is not None
    assert running.json()["finished_at"] is None

    succeeded = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "succeeded"},
    )
    assert succeeded.status_code == 200
    assert succeeded.json()["state"] == "succeeded"
    assert succeeded.json()["finished_at"] is not None


def test_transition_rejects_invalid_jump(client: TestClient) -> None:
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201
    created = create_run(client)
    assert created.status_code == 201

    response = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "succeeded"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXPERIMENT_NOT_READY"

    current = client.get("/api/v1/experiments/runs/run-api-1")
    assert current.json()["state"] == "pending"


def test_transition_missing_run_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/experiments/runs/missing-run/transitions",
        json={"to_state": "running"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_transition_rejects_terminal_state_change(
    client: TestClient,
) -> None:
    graph = client.post("/api/v1/graphs", json=make_graph_payload())
    assert graph.status_code == 201
    assert create_run(client).status_code == 201

    running = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "running"},
    )
    assert running.status_code == 200
    failed = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "failed", "error": "worker timeout"},
    )
    assert failed.status_code == 200
    assert failed.json()["error"] == "worker timeout"

    reopened = client.post(
        "/api/v1/experiments/runs/run-api-1/transitions",
        json={"to_state": "running"},
    )
    assert reopened.status_code == 422


@pytest.fixture
def client_with_db() -> Iterator[tuple[TestClient, Callable[[], Session]]]:
    """Provide a client plus direct database access for seeding results."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as test_client:
            yield test_client, lambda: Session(engine)
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        engine.dispose()


def seed_metric(session: Session, run_id: str) -> None:
    """Persist one metric record for a run."""
    save_metric_record(
        session,
        MetricRecord(
            metric_id="metric-accuracy",
            run_id=run_id,
            name="accuracy",
            value=0.92,
            result_kind=ResultKind.MEASURED,
        ),
    )
    session.commit()


def seed_artifact(session: Session, run_id: str) -> None:
    """Persist one artifact record for a run."""
    save_artifact_record(
        session,
        ArtifactRecord(
            artifact_id="artifact-checkpoint",
            run_id=run_id,
            kind="checkpoint",
            uri="file:///tmp/checkpoint",
            sha256="c" * 64,
            result_kind=ResultKind.MEASURED,
        ),
    )
    session.commit()


def test_list_run_metrics_returns_persisted_records(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, session_factory = client_with_db
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client).status_code == 201
    session = session_factory()
    try:
        seed_metric(session, "run-api-1")
    finally:
        session.close()

    response = client.get("/api/v1/experiments/runs/run-api-1/metrics")

    assert response.status_code == 200
    assert response.json() == [
        {
            "metric_id": "metric-accuracy",
            "run_id": "run-api-1",
            "name": "accuracy",
            "value": 0.92,
            "result_kind": "measured",
        }
    ]


def test_list_run_metrics_empty_without_results(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _session_factory = client_with_db
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client).status_code == 201

    response = client.get("/api/v1/experiments/runs/run-api-1/metrics")

    assert response.status_code == 200
    assert response.json() == []


def test_list_run_metrics_missing_run_returns_404(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _session_factory = client_with_db

    response = client.get("/api/v1/experiments/runs/missing-run/metrics")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_list_run_artifacts_returns_persisted_records(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, session_factory = client_with_db
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client).status_code == 201
    session = session_factory()
    try:
        seed_artifact(session, "run-api-1")
    finally:
        session.close()

    response = client.get("/api/v1/experiments/runs/run-api-1/artifacts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "artifact_id": "artifact-checkpoint",
            "run_id": "run-api-1",
            "kind": "checkpoint",
            "uri": "file:///tmp/checkpoint",
            "sha256": "c" * 64,
            "result_kind": "measured",
        }
    ]


def test_list_run_artifacts_missing_run_returns_404(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _session_factory = client_with_db

    response = client.get("/api/v1/experiments/runs/missing-run/artifacts")

    assert response.status_code == 404


def test_list_runs_filters_and_limits(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _session_factory = client_with_db
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client, run_id="run-api-1").status_code == 201
    assert create_run(client, run_id="run-api-2").status_code == 201

    all_runs = client.get("/api/v1/experiments/runs")
    assert all_runs.status_code == 200
    assert len(all_runs.json()) == 2

    filtered = client.get(
        "/api/v1/experiments/runs",
        params={"project_id": "project-api", "graph_id": "graph-api"},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 2

    empty = client.get(
        "/api/v1/experiments/runs", params={"project_id": "other-project"}
    )
    assert empty.status_code == 200
    assert empty.json() == []

    limited = client.get("/api/v1/experiments/runs", params={"limit": 1})
    assert limited.status_code == 200
    assert len(limited.json()) == 1

    invalid = client.get("/api/v1/experiments/runs", params={"limit": 0})
    assert invalid.status_code == 422


def test_compare_runs_returns_valid_comparison(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, session_factory = client_with_db
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client, run_id="run-baseline").status_code == 201
    assert create_run(client, run_id="run-variant").status_code == 201
    for run_id in ("run-baseline", "run-variant"):
        assert (
            client.post(
                f"/api/v1/experiments/runs/{run_id}/transitions",
                json={"to_state": "running"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/experiments/runs/{run_id}/transitions",
                json={"to_state": "succeeded"},
            ).status_code
            == 200
        )
    session = session_factory()
    try:
        save_metric_record(
            session,
            MetricRecord(
                metric_id="m-accuracy",
                run_id="run-baseline",
                name="accuracy",
                value=0.8,
                result_kind=ResultKind.MEASURED,
            ),
        )
        save_metric_record(
            session,
            MetricRecord(
                metric_id="m-accuracy",
                run_id="run-variant",
                name="accuracy",
                value=0.9,
                result_kind=ResultKind.MEASURED,
            ),
        )
        session.commit()
    finally:
        session.close()

    response = client.get(
        "/api/v1/experiments/comparisons",
        params={"baseline_run_id": "run-baseline", "variant_run_id": "run-variant"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "valid"
    assert body["metrics"][0]["name"] == "accuracy"
    assert body["metrics"][0]["absolute_change"] == pytest.approx(0.1)
    assert body["metrics"][0]["relative_change"] == pytest.approx(0.125)


def test_compare_runs_missing_run_returns_404(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _session_factory = client_with_db

    response = client.get(
        "/api/v1/experiments/comparisons",
        params={"baseline_run_id": "missing-run", "variant_run_id": "run-variant"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
