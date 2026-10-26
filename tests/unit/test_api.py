
"""API tests using an isolated in-memory database."""

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


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_retrieve_graph(client: TestClient) -> None:
    payload = make_graph_payload()

    created = client.post("/api/v1/graphs", json=payload)

    assert created.status_code == 201
    assert created.json()["graph_id"] == "graph-api"
    assert created.json()["version"] == 1

    retrieved = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/1"
    )

    assert retrieved.status_code == 200
    assert retrieved.json() == created.json()


def test_duplicate_initial_graph_returns_conflict(
    client: TestClient,
) -> None:
    payload = make_graph_payload()

    first = client.post("/api/v1/graphs", json=payload)
    duplicate = client.post("/api/v1/graphs", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "error" in duplicate.json()


def test_missing_revision_returns_404(client: TestClient) -> None:
    response = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/99"
    )

    assert response.status_code == 404


def test_invalid_graph_request_returns_422(client: TestClient) -> None:
    payload = make_graph_payload()
    payload["edges"] = [
        {"id": "edge-1", "source": "missing-node", "target": "encoder"}
    ]

    response = client.post("/api/v1/graphs", json=payload)

    assert response.status_code == 422
