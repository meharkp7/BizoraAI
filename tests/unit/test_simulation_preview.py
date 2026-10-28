"""Tests for pack simulation previews and preview routing."""

from typing import Any

from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.entity_service import preview_graph
from bizora.packs import deep_learning, electronics, iot


def make_node(node_id: str, label: str, **config: object) -> GraphNode:
    return GraphNode(id=node_id, kind=NodeKind.COMPONENT, label=label, config=dict(config))


def make_graph(
    title: str,
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...] = (),
) -> MethodologyGraph:
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title=title,
        nodes=nodes,
        edges=edges,
        created_by="tester",
    )


def divider_graph() -> MethodologyGraph:
    return make_graph(
        "Resistor divider circuit with voltage readout",
        (
            make_node(
                "v1",
                "Supply voltage",
                spice_kind="voltage-source",
                refdes="V1",
                nets=["in", "0"],
                voltage_v="5",
            ),
            make_node(
                "r1",
                "Resistor circuit",
                spice_kind="resistor",
                refdes="R1",
                nets=["in", "out"],
                resistance_ohm="1k",
            ),
            make_node(
                "r2",
                "Resistor circuit",
                spice_kind="resistor",
                refdes="R2",
                nets=["out", "0"],
                resistance_ohm="1k",
            ),
            make_node("d1", "Directive", spice_kind="directive", line=".op"),
        ),
    )


def linear_chain(entry_shape: tuple[int | None, ...], params: dict[str, Any]) -> MethodologyGraph:
    nodes: list[GraphNode] = [
        GraphNode(
            id="input",
            kind=NodeKind.INPUT,
            label="Input",
            output_shape=entry_shape,
        ),
        GraphNode(
            id="layer0",
            kind=NodeKind.MODEL,
            label="Linear layer with training gradient",
            config={"layer": "linear", **params},
        ),
        GraphNode(id="output", kind=NodeKind.OUTPUT, label="Output"),
    ]
    edges = (
        GraphEdge(id="e0", source="input", target="layer0"),
        GraphEdge(id="e1", source="layer0", target="output"),
    )
    return make_graph(
        "Transformer attention encoder training",
        tuple(nodes),
        edges,
    )


def test_electronics_preview_has_netlist_and_bom() -> None:
    preview = electronics.pack.simulation_preview(divider_graph())

    assert preview is not None
    assert preview.pack_id == "electronics"
    assert [section.heading for section in preview.sections] == [
        "Netlist",
        "Bill of materials (3 parts)",
    ]
    assert any("R1" in line for line in preview.sections[0].lines)
    assert any("R1" in line and "R2" in line for line in preview.sections[1].lines)


def test_electronics_preview_absent_without_simulatable_nodes() -> None:
    graph = make_graph("Unrelated notes", (make_node("n1", "Plain idea"),))

    assert electronics.pack.simulation_preview(graph) is None


def test_packs_without_builder_offer_no_preview() -> None:
    assert iot.pack.simulation_preview(divider_graph()) is None


def test_deep_learning_preview_shows_layers_and_source() -> None:
    graph = linear_chain((2, 8), {"in_features": 8, "out_features": 4})

    preview = deep_learning.pack.simulation_preview(graph)

    assert preview is not None
    assert preview.pack_id == "deep-learning"
    assert preview.sections[0].heading == "Layers (1)"
    assert "linear" in preview.sections[0].lines[0]
    assert any("nn.Linear" in line for line in preview.sections[1].lines)
    assert preview.warnings == ()


def test_deep_learning_preview_reports_compile_errors_as_warnings() -> None:
    graph = linear_chain((2, 4), {"in_features": 8, "out_features": 4})

    preview = deep_learning.pack.simulation_preview(graph)

    assert preview is not None
    assert preview.sections == ()
    assert len(preview.warnings) >= 1


def test_deep_learning_preview_absent_without_layers() -> None:
    graph = make_graph("Unrelated notes", (make_node("n1", "Plain idea"),))

    assert deep_learning.pack.simulation_preview(graph) is None


def test_preview_graph_routes_to_pack_preview() -> None:
    preview = preview_graph(divider_graph())

    assert preview is not None
    assert preview.pack_id == "electronics"


def test_preview_graph_returns_none_for_generic_graph() -> None:
    graph = make_graph("Unrelated notes", (make_node("n1", "Plain idea"),))

    assert preview_graph(graph) is None
