"""API tests for the experiment run lifecycle."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.db.base import Base
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
