"""API tests for revision history listing and restore-any-state."""

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
        "project_id": "project-history",
        "graph_id": "graph-history",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-history"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
        ],
        "edges": [{"id": "e1", "source": "input", "target": "encoder"}],
        "created_by": "test",
    }


def seed_two_revisions(client: TestClient) -> None:
    """Persist v1, then a v2 snapshot with the encoder removed."""
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    response = client.post(
        "/api/v1/graphs/project-history/graph-history/patch-batches",
        json={
            "patches": [
                {
                    "patch_id": "p1",
                    "base_graph_id": "graph-history",
                    "base_version": 1,
                    "operation": "remove_edge",
                    "target_id": "e1",
                    "payload": {},
                    "rationale": "Drop the encoder",
                    "requested_by": "test",
                },
                {
                    "patch_id": "p2",
                    "base_graph_id": "graph-history",
                    "base_version": 1,
                    "operation": "remove_node",
                    "target_id": "encoder",
                    "payload": {},
                    "rationale": "Drop the encoder",
                    "requested_by": "test",
                },
            ]
        },
    )
    assert response.status_code == 201


def test_list_revisions_returns_history_oldest_first(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.get("/api/v1/graphs/project-history/graph-history/revisions")

    assert response.status_code == 200
    rows = response.json()
    assert [row["version"] for row in rows] == [1, 2]
    assert rows[0]["parent_version"] is None
    assert rows[1]["parent_version"] == 1
    assert rows[0]["title"] == "Vision Transformer"
    assert rows[0]["created_by"] == "test"
    assert rows[0]["created_at"].endswith(("Z", "+00:00"))
    assert "nodes" not in rows[0]


def test_list_revisions_unknown_graph_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/graphs/missing/missing/revisions")

    assert response.status_code == 404


def test_restore_appends_head_with_old_content(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/1/restore",
        json={"requested_by": "restorer"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 3
    assert body["parent_version"] == 2
    assert body["created_by"] == "restorer"
    assert [node["id"] for node in body["nodes"]] == ["input", "encoder"]
    assert [edge["id"] for edge in body["edges"]] == ["e1"]


def test_restore_leaves_existing_revisions_untouched(client: TestClient) -> None:
    seed_two_revisions(client)
    before_v1 = client.get(
        "/api/v1/graphs/project-history/graph-history/revisions/1"
    ).json()
    before_v2 = client.get(
        "/api/v1/graphs/project-history/graph-history/revisions/2"
    ).json()

    restore = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/1/restore",
        json={"requested_by": "restorer"},
    )
    assert restore.status_code == 201

    after_v1 = client.get(
        "/api/v1/graphs/project-history/graph-history/revisions/1"
    ).json()
    after_v2 = client.get(
        "/api/v1/graphs/project-history/graph-history/revisions/2"
    ).json()
    assert after_v1 == before_v1
    assert after_v2 == before_v2


def test_restore_latest_revision_conflicts(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/2/restore",
        json={"requested_by": "restorer"},
    )

    assert response.status_code == 409


def test_restore_missing_revision_returns_404(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/9/restore",
        json={"requested_by": "restorer"},
    )

    assert response.status_code == 404


def test_restore_rejects_non_positive_version(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/0/restore",
        json={"requested_by": "restorer"},
    )

    assert response.status_code == 422


def test_restore_requires_requested_by(client: TestClient) -> None:
    seed_two_revisions(client)

    response = client.post(
        "/api/v1/graphs/project-history/graph-history/revisions/1/restore",
        json={},
    )

    assert response.status_code == 422
