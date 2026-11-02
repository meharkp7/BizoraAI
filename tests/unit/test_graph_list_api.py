"""API tests for the cross-paper graph list."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]


def _seed(client: TestClient, name: str) -> None:
    create = client.post("/api/v1/graphs", json=load_fixture_payload(name))
    assert create.status_code == 201


def test_list_graphs_reports_latest_revisions(client: TestClient) -> None:
    """Each graph appears once with its head version and counts."""
    _seed(client, "sram")
    _seed(client, "quant")

    response = client.get("/api/v1/graphs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    by_graph = {(entry["project_id"], entry["graph_id"]): entry for entry in body}
    quant = by_graph[("fixture-quant", "main")]
    assert quant["version"] == 1
    assert quant["node_count"] > 0
    assert quant["source_ids"]


def test_list_graphs_filters_by_project_and_source(client: TestClient) -> None:
    """Project and source filters narrow the tray candidates."""
    _seed(client, "sram")
    _seed(client, "quant")

    only_project = client.get("/api/v1/graphs", params={"project_id": "fixture-sram"})
    assert [entry["project_id"] for entry in only_project.json()] == ["fixture-sram"]

    listed = client.get("/api/v1/graphs").json()
    source_id = listed[0]["source_ids"][0]
    only_source = client.get("/api/v1/graphs", params={"source_id": source_id})
    assert only_source.json()
    assert all(source_id in entry["source_ids"] for entry in only_source.json())

    assert client.get("/api/v1/graphs", params={"source_id": "no-such-source"}).json() == []


def test_list_graphs_respects_limit(client: TestClient) -> None:
    """Limit caps the list at one entry."""
    _seed(client, "sram")
    _seed(client, "quant")

    response = client.get("/api/v1/graphs", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1
