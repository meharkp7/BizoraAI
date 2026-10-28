"""Tests for pack-routed 3D render specs."""

import pytest
from pydantic import ValidationError

from bizora.contracts.assets import NodeRenderSpec
from bizora.contracts.graph import GraphNode, MethodologyGraph, NodeKind
from bizora.core.entity_service import render_specs_for_graph


def make_node(node_id: str, label: str, **config: object) -> GraphNode:
    return GraphNode(id=node_id, kind=NodeKind.COMPONENT, label=label, config=dict(config))


def make_graph(title: str, nodes: tuple[GraphNode, ...]) -> MethodologyGraph:
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title=title,
        nodes=nodes,
        created_by="tester",
    )


def test_replaced_node_renders_catalog_package() -> None:
    graph = make_graph(
        "Resistor divider circuit with voltage readout",
        (
            make_node(
                "q1",
                "2N3904 NPN transistor",
                part="2N3904",
                device="NPN",
                package="TO-92",
            ),
        ),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].node_id == "q1"
    assert specs[0].illustrative is True
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.kind.value == "cylinder"
    assert len(specs[0].mesh.parts) == 4  # body + 3 leads


def test_package_falls_back_to_catalog_entry() -> None:
    graph = make_graph(
        "Resistor divider circuit with voltage readout",
        (make_node("q1", "2N3904 NPN transistor", part="2N3904"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.kind.value == "cylinder"


def test_exact_part_with_verified_package_renders() -> None:
    graph = make_graph(
        "Leakage monitor circuit with voltage readout",
        (make_node("m1", "INA219 current monitor", part="INA219"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].mesh is not None
    assert len(specs[0].mesh.parts) == 9  # body + 8 SOIC leads


def test_entry_default_footprint_covers_bare_labels() -> None:
    graph = make_graph(
        "Resistor divider circuit with voltage readout",
        (make_node("r1", "Resistor"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.body_length_mm == 1.6


def test_footprint_shorthand_maps_to_passive_row() -> None:
    graph = make_graph(
        "Resistor divider circuit with voltage readout",
        (make_node("r1", "Resistor", resistance_ohm=1000, footprint="0603"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.body_length_mm == 1.6


def make_ml_graph(nodes: tuple[GraphNode, ...]) -> MethodologyGraph:
    return make_graph("Pretrain a token model with backprop", nodes)


def test_ml_layer_renders_tensor_shape_slab() -> None:
    graph = make_ml_graph(
        (make_node("attn", "Attention block", layer="attention", embed_dim=768, num_heads=12),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].node_id == "attn"
    assert specs[0].label == "Attention"
    assert specs[0].illustrative is True
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.kind.value == "box"
    assert specs[0].mesh.spec.body_length_mm > specs[0].mesh.spec.body_height_mm


def test_ml_layer_binding_resolves_opaque_labels() -> None:
    graph = make_ml_graph(
        (
            make_node(
                "block-3",
                "block-3",
                layer="linear",
                in_features=128,
                out_features=512,
            ),
        ),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].label == "Linear"
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.body_length_mm > specs[0].mesh.spec.body_height_mm


def test_ml_text_match_resolves_labeled_layers() -> None:
    graph = make_ml_graph((make_node("lin", "Linear projection"),))

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].label == "Linear"
    assert specs[0].mesh is not None
    assert specs[0].mesh.spec.kind.value == "box"


def test_ml_unmatched_nodes_are_skipped() -> None:
    graph = make_ml_graph((make_node("mystery", "Xyzzq flurblewidget device"),))

    assert render_specs_for_graph(graph) == ()


def test_unresolved_nodes_are_skipped() -> None:
    graph = make_graph(
        "Resistor divider circuit with voltage readout",
        (make_node("mystery", "Xyzzq flurblewidget device"),),
    )

    assert render_specs_for_graph(graph) == ()


def test_generic_graph_yields_no_specs() -> None:
    graph = make_graph("Unrelated notes", (make_node("n1", "Plain idea"),))

    assert render_specs_for_graph(graph) == ()


def test_render_spec_requires_a_visual() -> None:
    with pytest.raises(ValidationError):
        NodeRenderSpec(node_id="n1", label="Nothing")
