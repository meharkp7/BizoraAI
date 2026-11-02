"""Tests for deterministic replication plans and the endpoint."""

from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]

from bizora.contracts.graph import MethodologyGraph
from bizora.core.replication import build_replication_plan, narrate_plan, order_nodes


def _graph(name: str) -> MethodologyGraph:
    return MethodologyGraph.model_validate(load_fixture_payload(name))


def test_plan_orders_steps_by_dependency() -> None:
    """Every edge's source step precedes its target step."""
    graph = _graph("quant")
    plan = build_replication_plan(graph)

    assert len(plan.steps) == len(graph.nodes)
    assert [step.seq for step in plan.steps] == list(range(1, len(graph.nodes) + 1))
    position = {step.node_id: step.seq for step in plan.steps}
    for edge in graph.edges:
        assert position[edge.source] < position[edge.target]


def test_plan_actions_carry_kind_verbs_and_verify_hints() -> None:
    """Steps name their kind's action and at least one check."""
    plan = build_replication_plan(_graph("sram"))

    for step in plan.steps:
        assert step.label in step.action
        assert step.node_id in step.action
        assert len(step.verify) >= 1


def test_plan_is_stable_without_edges() -> None:
    """Edgeless graphs keep declaration order."""
    graph = _graph("sram")
    bare = graph.model_copy(update={"edges": ()})

    assert [node.id for node in order_nodes(bare)] == [node.id for node in graph.nodes]


def test_plan_survives_cycles() -> None:
    """Cyclic graphs fall back to declaration order."""
    graph = _graph("sram")
    first, second = graph.nodes[0], graph.nodes[1]
    cycle = graph.model_copy(
        update={
            "edges": (
                *graph.edges,
                {
                    "id": "cycle-back",
                    "source": second.id,
                    "target": first.id,
                    "relation": "data_flow",
                    "evidence": [],
                },
            )
        }
    )
    revalidated = MethodologyGraph.model_validate(cycle.model_dump(mode="json"))

    assert [node.id for node in order_nodes(revalidated)] == [
        node.id for node in graph.nodes
    ]


def test_replication_plan_endpoint(client: TestClient) -> None:
    """The endpoint serves the latest revision's plan."""
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )

    response = client.get("/api/v1/projects/fixture-sram/graphs/main/replication-plan")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "fixture-sram"
    assert body["version"] == 1
    assert len(body["steps"]) == len(_graph("sram").nodes)
    assert body["steps"][0]["seq"] == 1


def test_replication_plan_unknown_graph_is_404(client: TestClient) -> None:
    """Missing graphs fail instead of planning nothing."""
    response = client.get("/api/v1/projects/nope/graphs/nope/replication-plan")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_narration_reads_every_step_in_order() -> None:
    """Each step gets one speakable line with its action and check."""
    plan = build_replication_plan(_graph("quant"))
    narration = narrate_plan(plan)

    assert narration.version == plan.version
    assert str(len(plan.steps)) in narration.intro
    assert len(narration.lines) == len(plan.steps)
    for line, step in zip(narration.lines, plan.steps, strict=True):
        assert line.seq == step.seq
        assert line.node_id == step.node_id
        assert f"Step {step.seq} of {len(plan.steps)}" in line.text
        assert step.action in line.text


def test_narration_endpoint(client: TestClient) -> None:
    """The endpoint serves the latest revision's build guide."""
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )

    response = client.get(
        "/api/v1/projects/fixture-sram/graphs/main/replication-plan/narration"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "fixture-sram"
    assert len(body["lines"]) == len(_graph("sram").nodes)
    assert body["lines"][0]["text"].startswith("Step 1 of")


def test_narration_unknown_graph_is_404(client: TestClient) -> None:
    """Missing graphs fail instead of narrating nothing."""
    response = client.get(
        "/api/v1/projects/nope/graphs/nope/replication-plan/narration"
    )

    assert response.status_code == 404
