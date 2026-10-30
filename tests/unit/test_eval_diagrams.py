"""Tests for the diagram eval script's pure metric helpers (no API)."""

import importlib.util
from pathlib import Path

import pytest

from bizora.contracts.diagram_ir import CircuitIR


def load_script():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / "scripts" / "eval_diagrams.py"
    spec = importlib.util.spec_from_file_location("eval_diagrams", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_circuit(payload_id: str, d_net: str = "n1") -> CircuitIR:
    return CircuitIR.model_validate(
        {
            "version": 1,
            "title": payload_id,
            "source": {"figure_id": "fig1", "page": 1},
            "components": [
                {
                    "id": "M1",
                    "type": "nmos",
                    "label": "M1",
                    "pins": {"d": d_net, "g": "n2", "s": "gnd"},
                    "confidence": 0.9,
                },
                {
                    "id": "R1",
                    "type": "resistor",
                    "label": "R1",
                    "pins": {"a": "n1", "b": "gnd"},
                    "confidence": 0.8,
                },
            ],
            "nets": [
                {"id": "gnd", "label": "GND", "role": "ground", "global": True},
                {"id": "n1", "label": "N1", "role": "signal", "global": False},
                {"id": "n2", "label": "N2", "role": "input", "global": False},
            ],
            "ports": [
                {"id": "P1", "net": "n2", "label": "IN", "dir": "in", "side": "left"},
            ],
        }
    )


def test_identical_circuits_score_perfectly() -> None:
    eval_diagrams = load_script()
    gold = make_circuit("gold")

    report = eval_diagrams.compare_circuit(make_circuit("pred"), gold)

    assert report["component_counts"]["match"] is True
    assert report["connectivity"]["f1"] == pytest.approx(1.0)


def test_rewired_pin_lowers_connectivity_f1() -> None:
    eval_diagrams = load_script()
    gold = make_circuit("gold")
    pred = make_circuit("pred", d_net="n2")

    report = eval_diagrams.compare_circuit(pred, gold)

    assert report["component_counts"]["match"] is True
    assert 0.0 < report["connectivity"]["f1"] < 1.0
    assert report["connectivity"]["matched"] == 1


def test_missing_component_type_shows_in_counts() -> None:
    eval_diagrams = load_script()
    gold = make_circuit("gold")
    raw = make_circuit("pred").model_dump(by_alias=True, mode="json")
    raw["components"] = [c for c in raw["components"] if c["type"] != "resistor"]
    pred = CircuitIR.model_validate(raw)

    report = eval_diagrams.compare_circuit(pred, gold)

    assert report["component_counts"]["match"] is False
    assert report["component_counts"]["missing"] == {"resistor": 1}
    assert report["component_counts"]["extra"] == {}


def test_disjoint_connectivity_scores_zero() -> None:
    eval_diagrams = load_script()
    gold = make_circuit("gold")
    raw = make_circuit("pred").model_dump(by_alias=True, mode="json")
    for component in raw["components"]:
        component["pins"] = {pin: f"x{pin}" for pin in component["pins"]}
        component["type"] = {"nmos": "pmos", "resistor": "capacitor"}[component["type"]]
    raw["nets"] = [
        {"id": "gnd", "label": "GND", "role": "ground", "global": True},
        *[
            {"id": f"x{pin}", "label": f"X{pin}", "role": "signal", "global": False}
            for pin in ("d", "g", "s", "a", "b")
        ],
    ]
    pred = CircuitIR.model_validate(raw)

    report = eval_diagrams.compare_circuit(pred, gold)

    assert report["connectivity"]["f1"] == pytest.approx(0.0)


def test_parse_crop_box_accepts_normalized_boxes() -> None:
    eval_diagrams = load_script()

    assert eval_diagrams.parse_crop_box("0,0,100,100") == (0.0, 0.0, 100.0, 100.0)
    assert eval_diagrams.parse_crop_box("5,10.5,50,60") == (5.0, 10.5, 50.0, 60.0)


@pytest.mark.parametrize(
    "bad", ["0,0,50", "a,b,c,d", "50,50,10,10", "-1,0,50,50", "0,0,101,50", "0,0,0,50"]
)
def test_parse_crop_box_rejects_bad_boxes(bad: str) -> None:
    eval_diagrams = load_script()

    with pytest.raises(ValueError):
        eval_diagrams.parse_crop_box(bad)


def test_load_gold_circuit_missing_file(tmp_path: Path) -> None:
    eval_diagrams = load_script()

    with pytest.raises(FileNotFoundError):
        eval_diagrams.load_gold_circuit(tmp_path / "nope.circuit.json")


def test_load_gold_circuit_round_trip(tmp_path: Path) -> None:
    eval_diagrams = load_script()
    path = tmp_path / "gold.circuit.json"
    path.write_text(make_circuit("gold").model_dump_json(by_alias=True), encoding="utf-8")

    assert eval_diagrams.load_gold_circuit(path) == make_circuit("gold")
