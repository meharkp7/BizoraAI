"""API tests for domain entities."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "domains"


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


def load_fixture_payload(name: str) -> dict[str, object]:
    """Load one domain fixture as a raw JSON payload."""
    raw = (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def test_entities_endpoint_returns_classification_and_resolutions(
    client: TestClient,
) -> None:
    """The entities endpoint classifies the graph and resolves every node."""
    create = client.post("/api/v1/graphs", json=load_fixture_payload("sram"))
    assert create.status_code == 201

    response = client.get("/api/v1/graphs/fixture-sram/main/revisions/1/entities")

    assert response.status_code == 200
    body = response.json()
    assert body["classification"]["domain"] == "electronics"
    assert body["project_id"] == "fixture-sram"
    assert body["graph_id"] == "main"
    assert body["version"] == 1
    by_node = {entity["node_id"]: entity for entity in body["entities"]}
    assert len(by_node) == 6
    assert by_node["sram-cell"]["entity_type"] == "memory-cell"
    assert by_node["sense-amplifier"]["entity_type"] == "sense-amplifier"


def test_entities_endpoint_missing_revision_returns_not_found(
    client: TestClient,
) -> None:
    """Unknown revisions report 404 instead of fabricated entities."""
    response = client.get("/api/v1/graphs/missing/main/revisions/1/entities")

    assert response.status_code == 404


def test_entities_endpoint_rejects_non_positive_version(client: TestClient) -> None:
    """Non-positive versions are rejected before any database lookup."""
    response = client.get("/api/v1/graphs/fixture-sram/main/revisions/0/entities")

    assert response.status_code == 422
