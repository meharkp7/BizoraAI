"""API tests for run reported-metrics quoted from graph tables."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_run_api import create_run, make_config_payload, make_graph_payload

from bizora.contracts.table import ExtractedTable
from bizora.db.base import Base
from bizora.db.repository import save_extracted_table
from bizora.db.session import get_db_session
from bizora.main import app


@pytest.fixture
def client_with_db() -> Iterator[tuple[TestClient, Callable[[], Session]]]:
    """Provide a client plus direct database access for seeding tables."""
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


def seed_table(session: Session) -> None:
    """Persist one results table for the API test graph."""
    save_extracted_table(
        session,
        ExtractedTable(
            table_id="table-1",
            project_id="project-api",
            graph_id="graph-api",
            source_id="paper-api",
            caption="CASP14 results.",
            columns=("Method", "TM-score"),
            rows=(("AlphaFold2", "0.92"), ("Baseline", "0.71")),
            page=4,
            created_by="researcher-1",
        ),
    )
    session.commit()


def seed_run(client: TestClient) -> None:
    """Persist the graph revision and run the endpoint reads through."""
    assert client.post("/api/v1/graphs", json=make_graph_payload()).status_code == 201
    assert create_run(client, config=make_config_payload()).status_code == 201


def test_list_run_reported_metrics_quotes_table_cells(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, session_factory = client_with_db
    seed_run(client)
    session = session_factory()
    try:
        seed_table(session)
    finally:
        session.close()

    response = client.get(
        "/api/v1/experiments/runs/run-api-1/reported-metrics",
        params={"names": ["tm-score"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [(entry["raw_value"], entry["value"]) for entry in payload] == [
        ("0.92", 0.92),
        ("0.71", 0.71),
    ]
    assert payload[0]["name"] == "tm-score"
    assert payload[0]["table_id"] == "table-1"
    assert payload[0]["page"] == 4


def test_list_run_reported_metrics_unknown_run_404s(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db

    response = client.get(
        "/api/v1/experiments/runs/run-nope/reported-metrics",
        params={"names": ["tm-score"]},
    )

    assert response.status_code == 404


def test_list_run_reported_metrics_empty_without_names_or_tables(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db
    seed_run(client)

    assert (
        client.get("/api/v1/experiments/runs/run-api-1/reported-metrics").json() == []
    )


def test_graph_reported_metrics_discovers_and_quotes(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """The graph endpoint discovers numbers, or quotes named ones."""
    client, session_factory = client_with_db
    session = session_factory()
    try:
        seed_table(session)
    finally:
        session.close()

    discovered = client.get("/api/v1/graphs/project-api/graph-api/reported-metrics")
    assert discovered.status_code == 200
    names = [entry["name"] for entry in discovered.json()]
    assert names == ["AlphaFold2 — TM-score", "Baseline — TM-score"]
    assert all(entry["table_id"] == "table-1" for entry in discovered.json())

    quoted = client.get(
        "/api/v1/graphs/project-api/graph-api/reported-metrics",
        params={"names": ["TM-score"]},
    )
    assert quoted.status_code == 200
    assert [entry["raw_value"] for entry in quoted.json()] == ["0.92", "0.71"]

    empty = client.get("/api/v1/graphs/unknown/graph/reported-metrics")
    assert empty.status_code == 200
    assert empty.json() == []
