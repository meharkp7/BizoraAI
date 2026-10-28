"""API tests for simulation previews and 3D render specs."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]


def _seed(client: TestClient, name: str) -> None:
    create = client.post("/api/v1/graphs", json=load_fixture_payload(name))
    assert create.status_code == 201


DIVIDER = {
    "project_id": "project-1",
    "graph_id": "divider",
    "version": 1,
    "title": "Resistor divider circuit with voltage readout",
    "created_by": "tester",
    "nodes": [
        {
            "id": "r1",
            "kind": "component",
            "label": "Resistor",
            "config": {"spice_kind": "resistor", "nets": ["in", "out"], "resistance_ohm": "1k"},
        },
        {"id": "d1", "kind": "component", "label": "Directive",
         "config": {"spice_kind": "directive", "line": ".op"}},
    ],
    "edges": [],
}


def test_preview_returns_null_when_absent(client: TestClient) -> None:
    """Revisions without a preview get 200 null, not 404 noise."""
    _seed(client, "sram")

    response = client.get("/api/v1/graphs/fixture-sram/main/revisions/1/simulation-preview")

    assert response.status_code == 200
    assert response.json() is None


def test_preview_returns_sections_for_simulatable_graph(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=DIVIDER)
    assert create.status_code == 201

    response = client.get("/api/v1/graphs/project-1/divider/revisions/1/simulation-preview")

    assert response.status_code == 200
    body = response.json()
    assert body["pack_id"] == "electronics"
    assert [section["heading"] for section in body["sections"]] == ["Netlist", "Bill of materials (1 part)"]


def test_preview_missing_revision_still_404s(client: TestClient) -> None:
    response = client.get("/api/v1/graphs/project-1/nope/revisions/1/simulation-preview")

    assert response.status_code == 404


def test_render_specs_returns_package_visuals(client: TestClient) -> None:
    create = client.post("/api/v1/graphs", json=DIVIDER)
    assert create.status_code == 201

    response = client.get("/api/v1/graphs/project-1/divider/revisions/1/render-specs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["node_id"] == "r1"
    assert body[0]["mesh"]["parts"][0]["name"] == "body"


def test_render_specs_empty_for_generic_graph(client: TestClient) -> None:
    create = client.post(
        "/api/v1/graphs",
        json={
            "project_id": "project-1",
            "graph_id": "notes",
            "version": 1,
            "title": "Unrelated notes",
            "created_by": "tester",
            "nodes": [{"id": "n1", "kind": "component", "label": "Plain idea"}],
            "edges": [],
        },
    )
    assert create.status_code == 201

    response = client.get("/api/v1/graphs/project-1/notes/revisions/1/render-specs")

    assert response.status_code == 200
    assert response.json() == []


def test_render_specs_missing_revision_404s(client: TestClient) -> None:
    response = client.get("/api/v1/graphs/project-1/nope/revisions/1/render-specs")

    assert response.status_code == 404
