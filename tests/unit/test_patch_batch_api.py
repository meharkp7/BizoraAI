"""API tests for atomic patch batches."""

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


def make_graph_payload() -> dict[str, object]:
    """Build a minimal graph request payload."""
    return {
        "project_id": "project-batch",
        "graph_id": "graph-batch",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-batch"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
        ],
        "edges": [{"id": "e1", "source": "input", "target": "encoder"}],
        "created_by": "test",
    }


def make_patch(
    patch_id: str,
    operation: str,
    *,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    base_version: int = 1,
) -> dict[str, Any]:
    """Build one patch payload against version 1."""
    return {
        "patch_id": patch_id,
        "base_graph_id": "graph-batch",
        "base_version": base_version,
        "operation": operation,
        "target_id": target_id,
        "payload": payload or {},
        "rationale": "Batch edit",
        "requested_by": "test",
    }


def batch_url() -> str:
    return "/api/v1/graphs/project-batch/graph-batch/patch-batches"


def test_batch_creates_exactly_one_revision(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.post(
        batch_url(),
        json={
            "patches": [
                make_patch("p1", "remove_edge", target_id="e1"),
                make_patch("p2", "remove_node", target_id="encoder"),
            ]
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 2
    assert body["parent_version"] == 1
    assert [node["id"] for node in body["nodes"]] == ["input"]
    assert body["edges"] == []

    # Exactly one revision was persisted; no intermediate version exists.
    assert (
        client.get(
            "/api/v1/graphs/project-batch/graph-batch/revisions/3"
        ).status_code
        == 404
    )


def test_failed_batch_persists_nothing(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.post(
        batch_url(),
        json={
            "patches": [
                make_patch(
                    "p1",
                    "update_node_config",
                    target_id="encoder",
                    payload={"config": {"layers": 12}},
                ),
                # Invalid: encoder still has a connected edge.
                make_patch("p2", "remove_node", target_id="encoder"),
            ]
        },
    )

    assert response.status_code == 422
    assert (
        client.get(
            "/api/v1/graphs/project-batch/graph-batch/revisions/2"
        ).status_code
        == 404
    )


def test_batch_rejects_path_mismatch(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.post(
        "/api/v1/graphs/project-batch/other-graph/patch-batches",
        json={"patches": [make_patch("p1", "remove_edge", target_id="e1")]},
    )
    assert response.status_code == 422


def test_batch_rejects_missing_base_revision(client: TestClient) -> None:
    response = client.post(
        batch_url(),
        json={"patches": [make_patch("p1", "remove_edge", target_id="e1")]},
    )
    assert response.status_code == 404


def test_batch_rejects_mixed_base_versions(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.post(
        batch_url(),
        json={
            "patches": [
                make_patch("p1", "remove_edge", target_id="e1"),
                make_patch(
                    "p2", "remove_node", target_id="encoder", base_version=2
                ),
            ]
        },
    )
    assert response.status_code == 422
