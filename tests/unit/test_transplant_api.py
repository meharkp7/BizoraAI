"""Tests for cross-graph transplant planning and the endpoint."""

import pytest
from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]

from bizora.contracts.graph import MethodologyGraph
from bizora.core.transplant import plan_transplant


def _graph(name: str) -> MethodologyGraph:
    return MethodologyGraph.model_validate(load_fixture_payload(name))


def test_plan_copies_nodes_and_internal_edges() -> None:
    """Internal edges move over; cut edges are counted, not kept."""
    source = _graph("quant")
    target = _graph("sram")
    first = source.nodes[0]
    internal = [
        edge
        for edge in source.edges
        if edge.source == first.id or edge.target == first.id
    ]

    plan = plan_transplant(source, target, [first.id])

    assert plan.added_node_ids == (first.id,)
    assert plan.renamed == {}
    assert plan.copied_edge_count == 0
    assert plan.dropped_edge_count == len(internal)
    assert len(plan.nodes) == len(target.nodes) + 1
    assert plan.title.startswith("Transplant 1 block from")


def test_plan_renames_colliding_ids() -> None:
    """Target ids win; transplanted copies take -tN suffixes."""
    source = _graph("quant")
    target = _graph("quant")
    node_id = source.nodes[0].id

    plan = plan_transplant(source, target, [node_id])

    assert plan.added_node_ids == (f"{node_id}-t1",)
    assert plan.renamed == {node_id: f"{node_id}-t1"}


def test_plan_rejects_unknown_nodes() -> None:
    """Missing source nodes fail with their ids."""
    with pytest.raises(KeyError) as exc:
        plan_transplant(_graph("quant"), _graph("sram"), ["no-such-node"])
    assert exc.value.args[0] == ["no-such-node"]


def test_transplant_endpoint_creates_a_new_revision(client: TestClient) -> None:
    """The endpoint persists the merged graph as the new head."""
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("quant")).status_code == 201
    )
    node_id = _graph("quant").nodes[0].id

    response = client.post(
        "/api/v1/graphs/fixture-sram/main/transplant",
        json={
            "source_project_id": "fixture-quant",
            "source_graph_id": "main",
            "node_ids": [node_id],
            "created_by": "cross-paper-ui",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 2
    assert body["added_node_ids"] == [node_id]

    head = client.get("/api/v1/graphs/fixture-sram/main/revisions/2")
    assert head.status_code == 200
    assert node_id in [node["id"] for node in head.json()["nodes"]]

    missing = client.post(
        "/api/v1/graphs/fixture-sram/main/transplant",
        json={
            "source_project_id": "fixture-quant",
            "source_graph_id": "main",
            "node_ids": ["no-such-node"],
            "created_by": "cross-paper-ui",
        },
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
