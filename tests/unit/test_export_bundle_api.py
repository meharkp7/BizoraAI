"""Tests for the graph export-bundle download."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]


def test_export_downloads_latest_revision(client: TestClient) -> None:
    """The bundle carries the full latest graph as an attachment."""
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )
    client.post(
        "/api/v1/projects/fixture-sram/memory",
        json={"fact": "The tapeout uses 65nm.", "created_by": "tester"},
    )

    response = client.get("/api/v1/projects/fixture-sram/graphs/main/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="fixture-sram-main-v1.json"'
    )
    body = response.json()
    assert body["bundle_version"] == "1.0"
    assert body["project_id"] == "fixture-sram"
    assert body["graph_id"] == "main"
    assert body["version"] == 1
    assert body["graph"]["graph_id"] == "main"
    assert len(body["graph"]["nodes"]) > 0
    assert [fact["fact"] for fact in body["memory"]] == ["The tapeout uses 65nm."]


def test_export_exports_latest_of_many_versions(client: TestClient) -> None:
    """A second revision moves the bundle head forward."""
    payload = dict(load_fixture_payload("sram"))
    initial = client.post("/api/v1/graphs", json=payload)
    assert initial.status_code == 201
    revised = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions", json=initial.json()
    )
    assert revised.status_code == 201

    response = client.get("/api/v1/projects/fixture-sram/graphs/main/export")

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["graph"]["title"] == initial.json()["title"]
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="fixture-sram-main-v2.json"'
    )


def test_export_unknown_graph_is_404(client: TestClient) -> None:
    """Missing graphs fail instead of exporting an empty bundle."""
    response = client.get("/api/v1/projects/nope/graphs/nope/export")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
