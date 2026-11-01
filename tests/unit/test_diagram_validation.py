"""Tests for diagram IR validators (one test per rule)."""

from typing import Any

from bizora.contracts.diagram_ir import (
    CircuitIR,
    MethodologyIR,
    StructureIR,
)
from bizora.core.diagram_validation import (
    normalize_structure_layout,
    validate_circuit,
    validate_diagram,
    validate_methodology,
    validate_structure,
)


def make_circuit(**overrides: Any) -> CircuitIR:
    base = {
        "version": 1,
        "title": "RC",
        "source": {"figure_id": "fig1", "page": 1},
        "components": [
            {
                "id": "M1",
                "type": "nmos",
                "label": "M1",
                "pins": {"d": "n1", "g": "n2", "s": "gnd"},
                "confidence": 0.9,
            },
            {
                "id": "R1",
                "type": "resistor",
                "label": "R1",
                "pins": {"a": "vdd", "b": "n1"},
                "confidence": 0.8,
            },
            {
                "id": "G1",
                "type": "ground",
                "label": "GND",
                "pins": {"g": "gnd"},
                "confidence": 1.0,
            },
        ],
        "nets": [
            {"id": "vdd", "label": "VDD", "role": "supply", "global": True},
            {"id": "gnd", "label": "GND", "role": "ground", "global": True},
            {"id": "n1", "label": "N1", "role": "signal", "global": False},
            {"id": "n2", "label": "N2", "role": "input", "global": False},
        ],
        "ports": [
            {"id": "P1", "net": "n2", "label": "IN", "dir": "in", "side": "left"},
        ],
    }
    base.update(overrides)
    return CircuitIR.model_validate(base)


def make_methodology(**overrides: Any) -> MethodologyIR:
    base = {
        "version": 1,
        "title": "flow",
        "groups": [{"id": "g1", "label": "stage"}],
        "nodes": [
            {"id": "n1", "label": "load", "kind": "input", "group": "g1",
             "confidence": 0.9},
            {"id": "n2", "label": "train", "kind": "model", "confidence": 0.8},
        ],
        "edges": [{"from": "n1", "to": "n2", "kind": "data"}],
    }
    base.update(overrides)
    return MethodologyIR.model_validate(base)


def make_block(**overrides: Any) -> StructureIR:
    base = {
        "id": "chip",
        "label": "chip",
        "kind": "chip",
        "confidence": 0.9,
        "children": [
            {
                "id": "arr",
                "label": "array",
                "kind": "array",
                "count": {"rows": 4, "cols": 4},
                "confidence": 0.8,
                "children": [
                    {
                        "id": "cell",
                        "label": "cell",
                        "kind": "cell",
                        "confidence": 0.7,
                        "children": [],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return StructureIR.model_validate(
        {"version": 1, "title": "struct", "root": base}
    )


def test_valid_circuit_has_no_errors_and_stats() -> None:
    result = validate_circuit(make_circuit())

    assert result.errors == ()
    assert result.warnings == ()
    assert result.is_valid is True
    assert result.stats["components"] == 3
    assert result.stats["nets"] == 4
    assert result.stats["ports"] == 1
    assert result.stats["connections"] == 7


def test_circuit_duplicate_ids_are_errors() -> None:
    ir = make_circuit()
    dup = ir.model_copy(
        update={"components": ir.components + (ir.components[0],)}
    )

    result = validate_circuit(dup)

    assert result.is_valid is False
    assert any("duplicate component id 'M1'" in e for e in result.errors)


def test_circuit_unknown_net_references_are_errors() -> None:
    ir = make_circuit()
    raw = ir.model_dump(by_alias=True, mode="json")
    raw["components"][0]["pins"]["d"] = "nope"
    raw["ports"][0]["net"] = "missing"
    raw["subcircuits"] = [{"id": "S1", "label": "s", "component_ids": ["ghost"]}]
    parsed = CircuitIR.model_validate(raw)

    result = validate_circuit(parsed)

    assert any("pin 'd' references unknown net 'nope'" in e for e in result.errors)
    assert any("port 'P1' references unknown net 'missing'" in e for e in result.errors)
    assert any("unknown component 'ghost'" in e for e in result.errors)


def test_circuit_missing_required_pins_are_errors() -> None:
    ir = make_circuit()
    no_gate = ir.components[0].model_copy(update={"pins": {"d": "n1", "s": "gnd"}})
    no_b = ir.components[1].model_copy(update={"pins": {"a": "vdd"}})
    mutated = ir.model_copy(update={"components": (no_gate, no_b, ir.components[2])})

    result = validate_circuit(mutated)

    assert any("missing required pin 'g'" in e for e in result.errors)
    assert any("missing required pin 'b'" in e for e in result.errors)


def test_circuit_block_accepts_any_pins() -> None:
    ir = make_circuit()
    block = {
        "id": "B1",
        "type": "block",
        "label": "custom",
        "pins": {"z": "n1", "q": "n2"},
        "confidence": 0.5,
    }
    parsed = CircuitIR.model_validate(
        {**ir.model_dump(by_alias=True), "components": [*ir.model_dump(by_alias=True)["components"], block]}
    )

    result = validate_circuit(parsed)

    assert result.errors == ()


def test_circuit_floating_pin_is_error() -> None:
    ir = make_circuit()
    floating = ir.components[0].model_copy(
        update={"pins": {"d": "", "g": "n2", "s": "gnd"}}
    )
    mutated = ir.model_copy(update={"components": (floating,) + ir.components[1:]})

    result = validate_circuit(mutated)

    assert any("floating" in e for e in result.errors)


def test_circuit_dangling_signal_net_is_error() -> None:
    ir = make_circuit()
    lonely = ir.components[0].model_copy(
        update={"pins": {"d": "solo", "g": "n2", "s": "gnd"}}
    )
    nets = [
        *ir.model_dump(by_alias=True)["nets"],
        {"id": "solo", "label": "SOLO", "role": "signal", "global": False},
    ]
    parsed = CircuitIR.model_validate(
        {**ir.model_dump(by_alias=True),
         "components": [lonely.model_dump(by_alias=True),
                        *[c.model_dump(by_alias=True) for c in ir.components[1:]]],
         "nets": nets}
    )

    result = validate_circuit(parsed)

    assert any("has only 1 connection" in e for e in result.errors)


def test_circuit_global_and_port_nets_are_not_dangling() -> None:
    result = validate_circuit(make_circuit())

    assert result.errors == ()


def test_circuit_requires_supply_or_ground_net() -> None:
    ir = make_circuit()
    no_rails = CircuitIR.model_validate(
        {**ir.model_dump(by_alias=True),
         "nets": [n for n in ir.model_dump(by_alias=True)["nets"]
                  if n["role"] not in ("supply", "ground")]}
    )

    result = validate_circuit(no_rails)

    assert any("no supply or ground net" in e for e in result.errors)


def test_pure_block_circuit_needs_no_rails() -> None:
    ir = CircuitIR.model_validate(
        {
            "version": 1,
            "title": "blocks",
            "source": {"figure_id": "derived-x", "page": 1},
            "components": [
                {
                    "id": "a",
                    "type": "block",
                    "label": "A",
                    "pins": {"out": "e0"},
                    "confidence": 0.4,
                },
                {
                    "id": "b",
                    "type": "block",
                    "label": "B",
                    "pins": {"in": "e0"},
                    "confidence": 0.4,
                },
            ],
            "nets": [{"id": "e0", "label": "flow", "role": "signal", "global": False}],
            "ports": [],
        }
    )

    result = validate_circuit(ir)

    assert result.errors == ()


def test_circuit_unexpected_pin_warns() -> None:
    ir = make_circuit()
    extra = ir.components[0].model_copy(
        update={"pins": {"d": "n1", "g": "n2", "s": "gnd", "x": "n1"}}
    )
    mutated = ir.model_copy(update={"components": (extra,) + ir.components[1:]})

    result = validate_circuit(mutated)

    assert result.errors == ()
    assert any("unexpected pin 'x'" in w for w in result.warnings)


def test_valid_methodology_has_no_errors_and_stats() -> None:
    result = validate_methodology(make_methodology())

    assert result.errors == ()
    assert result.warnings == ()
    assert result.stats == {"groups": 1, "nodes": 2, "edges": 1, "orphans": 0}


def test_methodology_duplicate_ids_are_errors() -> None:
    ir = make_methodology()
    dup = ir.model_copy(update={"nodes": ir.nodes + (ir.nodes[0],)})

    result = validate_methodology(dup)

    assert any("duplicate node id 'n1'" in e for e in result.errors)


def test_methodology_unknown_edge_endpoint_is_error() -> None:
    ir = make_methodology()
    bad = ir.edges[0].model_copy(update={"to": "ghost"})
    mutated = ir.model_copy(update={"edges": (bad,)})

    result = validate_methodology(mutated)

    assert any("unknown node 'ghost'" in e for e in result.errors)


def test_methodology_unknown_group_is_error() -> None:
    ir = make_methodology()
    bad = ir.nodes[0].model_copy(update={"group": "ghost"})
    mutated = ir.model_copy(update={"nodes": (bad, ir.nodes[1])})

    result = validate_methodology(mutated)

    assert any("unknown group 'ghost'" in e for e in result.errors)


def test_methodology_unknown_parent_group_is_error() -> None:
    ir = make_methodology()
    bad = ir.groups[0].model_copy(update={"parent": "ghost"})
    mutated = ir.model_copy(update={"groups": (bad,)})

    result = validate_methodology(mutated)

    assert any("unknown parent group 'ghost'" in e for e in result.errors)


def test_methodology_orphan_node_warns() -> None:
    ir = make_methodology()
    extra = {"id": "n3", "label": "side", "kind": "store", "confidence": 0.5}
    parsed = MethodologyIR.model_validate(
        {**ir.model_dump(by_alias=True),
         "nodes": [*ir.model_dump(by_alias=True)["nodes"], extra]}
    )

    result = validate_methodology(parsed)

    assert result.errors == ()
    assert any("orphan" in w for w in result.warnings)
    assert result.stats["orphans"] == 1


def test_valid_structure_has_no_errors_and_stats() -> None:
    result = validate_structure(make_block())

    assert result.errors == ()
    assert result.warnings == ()
    assert result.stats == {"blocks": 3, "max_depth": 2, "arrays": 1}


def test_structure_non_positive_count_is_error() -> None:
    assert any(
        "count" in e
        for e in validate_structure(make_block(count=0)).errors
    )
    raw = make_block().model_dump(mode="json")
    raw["root"]["children"][0]["count"] = {"rows": 0, "cols": 4}
    parsed = StructureIR.model_validate(raw)

    assert any("rows" in e for e in validate_structure(parsed).errors)


def test_structure_array_without_child_is_error() -> None:
    ir = make_block()
    childless = ir.root.children[0].model_copy(update={"children": ()})
    root = ir.root.model_copy(update={"children": (childless,)})
    parsed = StructureIR.model_validate(
        {"version": 1, "title": "struct", "root": root.model_dump(mode="json")}
    )

    result = validate_structure(parsed)

    assert any("no repeated cell child" in e for e in result.errors)


def test_structure_non_positive_dims_are_errors() -> None:
    parsed = make_block(dims={"w": -1, "h": 0, "unit": "um"})

    result = validate_structure(parsed)

    assert any("dims.w" in e for e in result.errors)
    assert any("dims.h" in e for e in result.errors)


def test_structure_array_root_without_grid_is_error() -> None:
    parsed = StructureIR.model_validate(
        {
            "version": 1,
            "title": "array only",
            "root": {
                "id": "arr",
                "label": "array",
                "kind": "array",
                "count": 2000,
                "confidence": 0.8,
                "children": [
                    {
                        "id": "cell",
                        "label": "cell",
                        "kind": "cell",
                        "confidence": 0.7,
                        "children": [],
                    }
                ],
            },
        }
    )

    result = validate_structure(parsed)

    assert any("without a rows/cols grid" in e for e in result.errors)


def test_structure_array_root_with_grid_or_blocks_is_clean() -> None:
    grid = StructureIR.model_validate(
        {
            "version": 1,
            "title": "array grid",
            "root": {
                "id": "arr",
                "label": "array",
                "kind": "array",
                "count": {"rows": 5, "cols": 400},
                "confidence": 0.8,
                "children": [
                    {
                        "id": "cell",
                        "label": "cell",
                        "kind": "cell",
                        "confidence": 0.7,
                        "children": [],
                    }
                ],
            },
        }
    )
    assert validate_structure(grid).errors == ()

    slab = StructureIR.model_validate(
        {
            "version": 1,
            "title": "array slab",
            "root": {
                "id": "arr",
                "label": "array",
                "kind": "array",
                "count": 2000,
                "confidence": 0.8,
                "children": [
                    {
                        "id": "cell",
                        "label": "cell",
                        "kind": "cell",
                        "confidence": 0.7,
                        "children": [],
                    },
                    {
                        "id": "peri",
                        "label": "periphery",
                        "kind": "periphery",
                        "confidence": 0.6,
                        "children": [],
                    },
                ],
            },
        }
    )
    assert validate_structure(slab).errors == ()


def test_validate_diagram_dispatches() -> None:
    assert validate_diagram(make_circuit()).stats["components"] == 3
    assert validate_diagram(make_methodology()).stats["nodes"] == 2
    assert validate_diagram(make_block()).stats["blocks"] == 3


def make_nested_structure() -> StructureIR:
    return StructureIR.model_validate(
        {
            "version": 1,
            "title": "chip",
            "root": {
                "id": "chip",
                "label": "chip",
                "kind": "chip",
                "confidence": 0.9,
                "children": [
                    {
                        "id": "arr",
                        "label": "array",
                        "kind": "array",
                        "count": {"rows": 4, "cols": 4},
                        "confidence": 0.8,
                        "children": [
                            {
                                "id": "cell",
                                "label": "cell",
                                "kind": "cell",
                                "confidence": 0.7,
                                "children": [],
                            },
                            {
                                "id": "gate",
                                "label": "OR gate",
                                "kind": "periphery",
                                "confidence": 0.8,
                                "children": [],
                            },
                        ],
                    },
                    {
                        "id": "ro",
                        "label": "readout",
                        "kind": "periphery",
                        "confidence": 0.8,
                        "children": [],
                    },
                ],
            },
        }
    )


def test_layout_hoists_shared_logic_from_arrays_to_root() -> None:
    arranged, notes = normalize_structure_layout(make_nested_structure())

    array = next(c for c in arranged.root.children if c.id == "arr")
    assert [c.id for c in array.children] == ["cell"]
    assert [c.id for c in arranged.root.children] == ["arr", "ro", "gate"]
    assert any("'gate'" in note for note in notes)


def test_layout_assigns_distinct_sides_to_unplaced_blocks() -> None:
    arranged, notes = normalize_structure_layout(make_nested_structure())

    by_id = {c.id: c for c in arranged.root.children}
    assert by_id["arr"].pos is None
    assert by_id["ro"].pos == "bottom"
    assert by_id["gate"].pos == "right"
    assert any("illustratively" in note for note in notes)


def test_layout_keeps_explicit_pos_and_skips_taken_sides() -> None:
    ir = make_nested_structure()
    kids = tuple(
        c.model_copy(update={"pos": "bottom"}) if c.id == "ro" else c
        for c in ir.root.children
    )
    ir = ir.model_copy(
        update={"root": ir.root.model_copy(update={"children": kids})}
    )

    arranged, _ = normalize_structure_layout(ir)

    by_id = {c.id: c for c in arranged.root.children}
    assert by_id["ro"].pos == "bottom"
    assert by_id["gate"].pos == "right"


def test_layout_leaves_placed_trees_untouched() -> None:
    ir = make_block()

    arranged, notes = normalize_structure_layout(ir)

    assert arranged == ir
    assert notes == ()
