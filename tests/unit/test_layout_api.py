"""API tests for visual-only graph layouts."""

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
        "project_id": "project-layout",
        "graph_id": "graph-layout",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-layout"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
        ],
        "edges": [{"id": "e1", "source": "input", "target": "encoder"}],
        "created_by": "test",
    }


def make_layout_payload() -> dict[str, object]:
    """Build a minimal layout request payload."""
    return {
        "project_id": "project-layout",
        "graph_id": "graph-layout",
        "version": 1,
        "positions": [
            {"node_id": "input", "x": 10.0, "y": 20.0},
            {"node_id": "encoder", "x": 30.0, "y": 40.0, "z": 5.0},
        ],
        "viewport": {"x": 0.0, "y": 0.0, "zoom": 1.0},
        "camera": None,
        "updated_by": "test",
    }


def layout_url() -> str:
    return "/api/v1/graphs/project-layout/graph-layout/revisions/1/layout"


def test_layout_round_trip_and_no_new_revision(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=make_graph_payload())
    assert create.status_code == 201

    saved = client.put(layout_url(), json=make_layout_payload())
    assert saved.status_code == 200
    assert saved.json()["positions"][0]["node_id"] == "input"

    retrieved = client.get(layout_url())
    assert retrieved.status_code == 200
    assert retrieved.json() == saved.json()

    # Saving a layout must not create a graph revision.
    assert client.get(layout_url().replace("/layout", "")).status_code == 200
    missing_revision = client.get(
        "/api/v1/graphs/project-layout/graph-layout/revisions/2"
    )
    assert missing_revision.status_code == 404


def test_missing_layout_returns_not_found(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=make_graph_payload())
    assert create.status_code == 201

    response = client.get(layout_url())
    assert response.status_code == 404


def test_layout_for_missing_revision_returns_not_found(
    client: TestClient,
) -> None:
    response = client.put(layout_url(), json=make_layout_payload())
    assert response.status_code == 404


def test_layout_path_mismatch_rejected(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=make_graph_payload())
    assert create.status_code == 201

    payload = make_layout_payload()
    payload["version"] = 2
    response = client.put(layout_url(), json=payload)
    assert response.status_code == 422


def test_layout_unknown_node_rejected(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=make_graph_payload())
    assert create.status_code == 201

    payload = make_layout_payload()
    payload["positions"] = [{"node_id": "ghost", "x": 1.0, "y": 2.0}]
    response = client.put(layout_url(), json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["unknown_node_ids"] == ["ghost"]
