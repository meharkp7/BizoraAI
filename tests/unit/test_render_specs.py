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


def make_iot_graph(nodes: tuple[GraphNode, ...]) -> MethodologyGraph:
    return make_graph("ESP32 sensor gateway with MQTT firmware", nodes)


def test_iot_module_renders_shielded_assembly() -> None:
    graph = make_iot_graph((make_node("mcu", "ESP32-WROOM-32 module"),))

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].label == "ESP32-WROOM-32 module"
    assert specs[0].fallback_package == "ESP32-WROOM-32"
    assert specs[0].illustrative is True
    assert specs[0].mesh is not None
    names = [part.name for part in specs[0].mesh.parts]
    assert names[0] == "pcb"
    assert names[-1] == "can"
    assert len(names) == 1 + 38 + 1
    pcb_top = max(v[1] for v in specs[0].mesh.parts[0].vertices)
    can_bottom = min(v[1] for v in specs[0].mesh.parts[-1].vertices)
    assert can_bottom == pytest.approx(pcb_top)


def test_uno_renders_board_assembly() -> None:
    graph = make_iot_graph((make_node("board", "Arduino Uno R3"),))

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].fallback_package == "Arduino Uno R3"
    assert specs[0].mesh is not None
    names = [part.name for part in specs[0].mesh.parts]
    assert names[0] == "pcb"
    assert "usb" in names
    assert "body" in names
    assert len(names) == 1 + 1 + (1 + 28) + 4
    bounds = specs[0].mesh.bounds
    assert bounds.min_xyz[0] >= -34.3 and bounds.max_xyz[0] <= 34.3
    assert bounds.min_xyz[2] >= -26.7 and bounds.max_xyz[2] <= 26.7


def test_to220_renders_body_tab_and_leads() -> None:
    graph = make_graph(
        "Resistor divider circuit with resistor tolerance",
        (make_node("q1", "Switching MOSFET", part="IRF540N"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].fallback_package == "TO-220"
    assert specs[0].mesh is not None
    names = [part.name for part in specs[0].mesh.parts]
    assert names == ["body", "pin-1", "pin-2", "pin-3", "tab"]
    body_top = max(v[1] for v in specs[0].mesh.parts[0].vertices)
    tab_bottom = min(v[1] for v in specs[0].mesh.parts[-1].vertices)
    assert tab_bottom == pytest.approx(body_top)


def test_parts_without_visuals_keep_package_fallback() -> None:
    graph = make_graph(
        "Resistor divider circuit with resistor tolerance",
        (make_node("r1", "Resistor"),),
    )

    specs = render_specs_for_graph(graph)

    assert len(specs) == 1
    assert specs[0].fallback_package == "resistor-generic"
    assert specs[0].mesh is not None
    assert [part.name for part in specs[0].mesh.parts] == ["body", "pin-1", "pin-2"]


def test_all_part_visuals_build_within_mesh_caps() -> None:
    from bizora.assets.procedural import build_assembly
    from bizora.packs import electronics, iot

    for module in (electronics, iot):
        for component_id, solids in module.VISUAL_SPECS.items():
            mesh = build_assembly(solids)
            assert len(mesh.parts) <= 64, component_id
            assert mesh.vertex_count <= 65536, component_id


def test_all_part_visuals_carry_outline_source_and_note() -> None:
    from bizora.packs import electronics, iot

    for module in (electronics, iot):
        assert module.PART_VISUALS, module.__name__
        for component_id, row in module.PART_VISUALS.items():
            assert row["outline"], component_id
            assert row["source"], component_id
            assert row["note"], component_id
            assert row["solids"], component_id


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
