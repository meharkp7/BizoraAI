"""API tests for revision diffs."""

from collections.abc import Iterator

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
        "project_id": "project-diff",
        "graph_id": "graph-diff",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-diff"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
        ],
        "edges": [{"id": "e1", "source": "input", "target": "encoder"}],
        "created_by": "test",
    }


def make_add_node_patch() -> dict[str, object]:
    """Build a patch that adds one node to version 1."""
    return {
        "patch_id": "patch-diff-1",
        "base_graph_id": "graph-diff",
        "base_version": 1,
        "operation": "add_node",
        "target_id": None,
        "payload": {
            "node": {
                "id": "head",
                "kind": "output",
                "label": "Head",
            }
        },
        "rationale": "Add output head",
        "requested_by": "test",
    }


def test_diff_between_revisions(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    patched = client.post(
        "/api/v1/graphs/project-diff/graph-diff/patches",
        json=make_add_node_patch(),
    )
    assert patched.status_code == 201

    response = client.get(
        "/api/v1/graphs/project-diff/graph-diff/diff",
        params={"base_version": 1, "target_version": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["base_version"] == 1
    assert body["target_version"] == 2
    assert [node["id"] for node in body["added_nodes"]] == ["head"]
    assert body["removed_nodes"] == []
    assert body["changed_nodes"] == []


def test_diff_same_revision_is_empty(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.get(
        "/api/v1/graphs/project-diff/graph-diff/diff",
        params={"base_version": 1, "target_version": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["added_nodes"] == []
    assert body["removed_nodes"] == []
    assert body["changed_nodes"] == []
    assert body["added_edges"] == []
    assert body["removed_edges"] == []
    assert body["changed_edges"] == []


def test_diff_missing_revision_returns_not_found(client: TestClient) -> None:
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201

    response = client.get(
        "/api/v1/graphs/project-diff/graph-diff/diff",
        params={"base_version": 1, "target_version": 9},
    )
    assert response.status_code == 404


def test_diff_rejects_non_positive_versions(client: TestClient) -> None:
    response = client.get(
        "/api/v1/graphs/project-diff/graph-diff/diff",
        params={"base_version": 0, "target_version": 1},
    )
    assert response.status_code == 422
