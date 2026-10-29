"""API tests for the component library, preflight, copilot, and adapters."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]


def _seed(client: TestClient, name: str) -> None:
    create = client.post("/api/v1/graphs", json=load_fixture_payload(name))
    assert create.status_code == 201


def test_list_components_searches_and_filters(client: TestClient) -> None:
    """The library endpoint searches text and filters domain and identity."""
    response = client.get("/api/v1/components", params={"q": "2N3904"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["component_id"] == "npn-2n3904"
    assert body[0]["generic"] is False

    generics = client.get("/api/v1/components", params={"domain": "electronics", "generic": True})
    assert generics.status_code == 200
    assert generics.json()
    assert all(entry["generic"] for entry in generics.json())


def test_get_component_detail_returns_specs_and_schema(client: TestClient) -> None:
    """Component detail carries pinout, interfaces, and config schema."""
    response = client.get("/api/v1/components/sense-ina219")

    assert response.status_code == 200
    body = response.json()
    assert body["part_number"] == "INA219"
    assert body["reference_url"] == "https://www.ti.com/product/INA219"
    assert any(pin["name"] == "SDA" for pin in body["pinout"])
    assert any(field["key"] == "shunt_ohm" for field in body["config_schema"])


def test_get_component_detail_missing_returns_not_found(client: TestClient) -> None:
    """Unknown component ids report 404."""
    response = client.get("/api/v1/components/no-such-part")

    assert response.status_code == 404


def test_preflight_endpoint_validates_without_writing(client: TestClient) -> None:
    """Preflight approves a compatible swap and names preserved edges."""
    _seed(client, "sram")
    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/nodes/access-transistors/preflight",
        json={"component_id": "npn-2n3904", "config": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["compatible"] is True
    assert body["candidate"]["entity_type"] == "transistor"

    revision = client.get("/api/v1/graphs/fixture-sram/main/revisions/1")
    assert revision.json()["version"] == 1


def test_preflight_endpoint_reports_incompatibility(client: TestClient) -> None:
    """Preflight names the dropped interfaces for an invalid swap."""
    _seed(client, "sram")
    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/nodes/sense-amplifier/preflight",
        json={"component_id": "psu-vdd-generic", "config": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["compatible"] is False
    assert {missing["kind"] for missing in body["missing_interfaces"]} >= {"data", "analog"}


def test_preflight_endpoint_rejects_unknown_component(client: TestClient) -> None:
    """Unknown components report 404 with the standard error shape."""
    _seed(client, "sram")
    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/nodes/sram-cell/preflight",
        json={"component_id": "no-such-part", "config": {}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_removal_preflight_endpoint_reports_blast_radius(client: TestClient) -> None:
    """Removal preflight names neighbors, dropped edges, and paper claims."""
    _seed(client, "sram")
    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/nodes/sense-amplifier/removal-preflight",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_node_id"] == "sense-amplifier"
    assert body["neighbor_node_ids"] == ["sram-cell", "leakage-monitor"]
    assert body["dropped_edge_ids"] == ["e-cell-sense", "e-sense-monitor"]
    assert body["evidence"]

    revision = client.get("/api/v1/graphs/fixture-sram/main/revisions/1")
    assert revision.json()["version"] == 1


def test_removal_preflight_endpoint_rejects_unknown_node(client: TestClient) -> None:
    """Unknown nodes report 404 with the standard error shape."""
    _seed(client, "sram")
    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/nodes/no-such-node/removal-preflight",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_copilot_endpoint_answers_from_graph_state(client: TestClient) -> None:
    """Copilot replacements validate and propose without applying."""
    _seed(client, "quant")
    response = client.post(
        "/api/v1/graphs/fixture-quant/main/revisions/1/copilot",
        json={"message": "replace nf4-quantizer with FP16"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["component_id"] == "format-fp16"
    assert body["proposal"]["node_id"] == "nf4-quantizer"
    assert any(card["kind"] == "proposal" for card in body["cards"])


def test_list_adapters_reports_registered_adapters(client: TestClient) -> None:
    """The adapters endpoint exposes exactly the registered execution adapters."""
    response = client.get("/api/v1/experiments/adapters")

    assert response.status_code == 200
    body = response.json()
    assert any(
        entry["adapter_id"] == "bizora.deterministic-test" and entry["adapter_version"] == "0.1.0"
        for entry in body
    )
