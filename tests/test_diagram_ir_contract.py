"""Contract tests for the diagram intermediate representations (IRs)."""

import json

import pytest
from pydantic import ValidationError

from bizora.contracts.diagram_ir import (
    CIRCUIT_IR_JSON_SCHEMA,
    METHODOLOGY_IR_JSON_SCHEMA,
    STRUCTURE_IR_JSON_SCHEMA,
    ArrayCount,
    CircuitIR,
    MethodologyIR,
    StructureIR,
)


def make_circuit() -> dict:
    return {
        "version": 1,
        "title": "6T SRAM bitcell",
        "source": {"figure_id": "fig1", "page": 2},
        "components": [
            {
                "id": "M1",
                "type": "nmos",
                "label": "M1",
                "pins": {"d": "bl", "g": "wl", "s": "gnd"},
                "placement": {"x": 30, "y": 40, "rot": 0, "mirror": False, "flip": False},
                "confidence": 0.9,
                "evidence": {"figure_id": "fig1", "bbox": [25, 35, 35, 45]},
            },
            {
                "id": "R1",
                "type": "resistor",
                "label": "R1",
                "value": "1k",
                "pins": {"a": "vdd", "b": "bl"},
                "confidence": 0.8,
            },
            {
                "id": "GND1",
                "type": "ground",
                "label": "GND",
                "pins": {"g": "gnd"},
                "confidence": 1.0,
            },
            {
                "id": "B1",
                "type": "block",
                "label": "sense amp",
                "pins": {"inp": "bl", "out": "dout"},
                "pin_sides": {"inp": "left", "out": "right"},
                "confidence": 0.5,
            },
        ],
        "nets": [
            {"id": "vdd", "label": "VDD", "role": "supply", "global": True},
            {"id": "gnd", "label": "GND", "role": "ground", "global": True},
            {"id": "bl", "label": "BL", "role": "signal", "global": False},
            {"id": "wl", "label": "WL", "role": "input", "global": False},
            {"id": "dout", "label": "DOUT", "role": "output", "global": False},
        ],
        "ports": [
            {
                "id": "P_WL",
                "net": "wl",
                "label": "WL",
                "dir": "in",
                "side": "left",
                "placement": {"x": 0, "y": 50},
            }
        ],
        "subcircuits": [{"id": "SC1", "label": "cell", "component_ids": ["M1", "R1"]}],
        "layout": {"unit": 1.0},
    }


def make_methodology() -> dict:
    return {
        "version": 1,
        "title": "PUF evaluation flow",
        "groups": [
            {"id": "g1", "label": "enrollment"},
            {"id": "g2", "label": "eval", "parent": "g1"},
        ],
        "nodes": [
            {
                "id": "n1",
                "label": "collect responses",
                "kind": "input",
                "group": "g1",
                "detail": "read bitcells",
                "params": {"reads": 100},
                "confidence": 0.9,
                "evidence": {"page": 3, "quote": "responses were collected"},
            },
            {"id": "n2", "label": "train model", "kind": "model", "confidence": 0.7},
            {"id": "n3", "label": "bit error?", "kind": "decision", "confidence": 0.6},
        ],
        "edges": [
            {"from": "n1", "to": "n2", "label": "responses", "kind": "data"},
            {"from": "n2", "to": "n3", "kind": "control"},
        ],
    }


def make_structure() -> dict:
    return {
        "version": 1,
        "title": "SRAM macro",
        "root": {
            "id": "chip",
            "label": "macro",
            "kind": "chip",
            "dims": {"w": 100, "h": 80, "d": 5, "unit": "um"},
            "pos": "center",
            "confidence": 0.9,
            "children": [
                {
                    "id": "arr",
                    "label": "bitcell array",
                    "kind": "array",
                    "count": {"rows": 16, "cols": 16},
                    "pos": {"x": 50, "y": 50},
                    "tensor_shape": [16, 16],
                    "confidence": 0.85,
                    "children": [
                        {
                            "id": "cell",
                            "label": "6T cell",
                            "kind": "cell",
                            "part": "bitcell",
                            "confidence": 0.8,
                            "children": [],
                        }
                    ],
                },
                {
                    "id": "peri",
                    "label": "periphery",
                    "kind": "periphery",
                    "count": 2,
                    "pos": "bottom",
                    "confidence": 0.6,
                    "children": [],
                },
            ],
        },
    }


def test_valid_circuit_ir_round_trip() -> None:
    ir = CircuitIR.model_validate(make_circuit())

    assert ir.version == 1
    assert ir.components[0].type == "nmos"
    assert ir.nets[0].is_global is True
    dumped = ir.model_dump(by_alias=True)
    assert dumped["nets"][0]["global"] is True
    assert CircuitIR.model_validate(dumped) == ir


def test_valid_methodology_ir_round_trip() -> None:
    ir = MethodologyIR.model_validate(make_methodology())

    assert ir.nodes[0].kind == "input"
    assert ir.edges[0].from_node == "n1"
    dumped = ir.model_dump(by_alias=True)
    assert dumped["edges"][0]["from"] == "n1"
    assert MethodologyIR.model_validate(dumped) == ir


def test_valid_structure_ir_round_trip() -> None:
    ir = StructureIR.model_validate(make_structure())

    assert ir.root.kind == "chip"
    assert ir.root.children[0].count == ArrayCount(rows=16, cols=16)
    assert ir.root.children[1].count == 2
    dumped = ir.model_dump(mode="json")
    assert StructureIR.model_validate(dumped) == ir


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["components"].__setitem__(0, {**c["components"][0], "type": "transistor"}),
        lambda c: c["components"].__setitem__(
            0, {**c["components"][0], "confidence": 1.5}
        ),
        lambda c: c["components"].__setitem__(
            0,
            {**c["components"][0], "placement": {"x": 0, "y": 0, "rot": 45}},
        ),
        lambda c: c["components"].__setitem__(
            0, {**c["components"][0], "pins": {"d": 5}}
        ),
        lambda c: c["nets"].__setitem__(0, {**c["nets"][0], "role": "power"}),
        lambda c: c["ports"].__setitem__(0, {**c["ports"][0], "dir": "sideways"}),
        lambda c: c["ports"].__setitem__(0, {**c["ports"][0], "side": "middle"}),
        lambda c: c.update({"version": 2}),
        lambda c: c["components"].__setitem__(
            0, {**c["components"][0], "bogus": "nope"}
        ),
        lambda c: c["components"].__setitem__(0, {**c["components"][0], "id": ""}),
    ],
)
def test_invalid_circuit_ir_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    circuit = make_circuit()
    mutate(circuit)

    with pytest.raises(ValidationError):
        CircuitIR.model_validate(circuit)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["nodes"].__setitem__(0, {**m["nodes"][0], "kind": "magic"}),
        lambda m: m["nodes"].__setitem__(0, {**m["nodes"][0], "confidence": -0.1}),
        lambda m: m["edges"].__setitem__(0, {"from": "n1", "kind": "data"}),
        lambda m: m["edges"].__setitem__(0, {**m["edges"][0], "kind": "wire"}),
        lambda m: m["nodes"].__setitem__(0, {**m["nodes"][0], "id": ""}),
        lambda m: m.update({"title": ""}),
    ],
)
def test_invalid_methodology_ir_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    methodology = make_methodology()
    mutate(methodology)

    with pytest.raises(ValidationError):
        MethodologyIR.model_validate(methodology)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["root"].update({"kind": "blob"}),
        lambda s: s["root"]["children"][0].update({"count": "16x16"}),
        lambda s: s["root"]["children"][0].update({"pos": "behind"}),
        lambda s: s["root"].update({"confidence": 2.0}),
        lambda s: s["root"]["children"][0].update({"tensor_shape": ["a"]}),
        lambda s: s["root"].update({"id": ""}),
    ],
)
def test_invalid_structure_ir_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    structure = make_structure()
    mutate(structure)

    with pytest.raises(ValidationError):
        StructureIR.model_validate(structure)


def test_exported_json_schemas_cover_all_irs() -> None:
    for name, schema in (
        ("CircuitIR", CIRCUIT_IR_JSON_SCHEMA),
        ("MethodologyIR", METHODOLOGY_IR_JSON_SCHEMA),
        ("StructureIR", STRUCTURE_IR_JSON_SCHEMA),
    ):
        assert schema["title"] == name
        assert schema["type"] == "object"
        assert "version" in schema["properties"]
        json.dumps(schema)  # must be JSON-serializable for the Responses API


def test_circuit_schema_lists_components_nets_ports() -> None:
    props = CIRCUIT_IR_JSON_SCHEMA["properties"]

    assert {"components", "nets", "ports"} <= set(props)
    assert set(CIRCUIT_IR_JSON_SCHEMA["required"]) >= {
        "version",
        "title",
        "source",
        "components",
        "nets",
        "ports",
    }
