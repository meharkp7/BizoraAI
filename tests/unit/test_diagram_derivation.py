"""Tests for deterministic methodology-derived diagrams."""

import pytest

from bizora.contracts.diagram_ir import (
    ComponentType,
    MethodologyEdge,
    MethodologyEvidence,
    MethodologyGroup,
    MethodologyIR,
    MethodologyNode,
    MethodologyNodeKind,
)
from bizora.core.diagram_derivation import (
    DERIVED_CONFIDENCE,
    methodology_to_circuit,
    methodology_to_structure,
)
from bizora.core.diagram_validation import validate_diagram


def make_methodology(*, with_figure: bool = True) -> MethodologyIR:
    """Three steps across two groups: raw -> encode -> score, plus a loner."""
    evidence = (
        MethodologyEvidence(page=2, figure_id="fig-flow", quote="We encode, then score.")
        if with_figure
        else None
    )
    return MethodologyIR(
        version=1,
        title="Toy pipeline",
        groups=(
            MethodologyGroup(id="prep", label="Preparation"),
            MethodologyGroup(id="infer", label="Inference"),
        ),
        nodes=(
            MethodologyNode(
                id="raw",
                label="Load raw responses",
                kind=MethodologyNodeKind.INPUT,
                group="prep",
                confidence=0.9,
                evidence=evidence,
            ),
            MethodologyNode(
                id="encode",
                label="Encode with a transformer",
                kind=MethodologyNodeKind.MODEL,
                group="infer",
                detail="12 layers, mean pooling.",
                confidence=0.8,
                evidence=evidence,
            ),
            MethodologyNode(
                id="score",
                label="Score against labels",
                kind=MethodologyNodeKind.EVALUATION,
                group="infer",
                confidence=0.8,
                evidence=evidence,
            ),
            MethodologyNode(
                id="loner",
                label="Unconnected audit",
                kind=MethodologyNodeKind.OUTPUT,
                confidence=0.7,
                evidence=evidence,
            ),
        ),
        edges=(
            MethodologyEdge(from_node="raw", to="encode", label="responses"),
            MethodologyEdge(from_node="encode", to="score"),
        ),
    )


def test_derived_circuit_maps_steps_to_blocks_and_edges_to_nets() -> None:
    circuit = methodology_to_circuit(make_methodology(), source_id="paper-x")

    assert circuit is not None
    assert circuit.title == "Toy pipeline (system blocks)"
    assert [component.id for component in circuit.components] == [
        "raw",
        "encode",
        "score",
        "loner",
    ]
    assert all(component.type is ComponentType.BLOCK for component in circuit.components)
    assert circuit.components[1].pins == {"in": "e0", "out": "e1"}
    # Every net joins exactly two block pins; the loner gets a ported solo net.
    assert [(net.id, net.role.value) for net in circuit.nets] == [
        ("e0", "signal"),
        ("e1", "signal"),
        ("solo0", "signal"),
    ]
    assert circuit.components[3].pins == {"io": "solo0"}
    assert [(port.net, port.dir.value) for port in circuit.ports] == [("solo0", "out")]
    assert circuit.components[0].evidence is not None
    assert "Derived from methodology step" in (circuit.components[0].evidence.quote or "")
    assert all(component.confidence == DERIVED_CONFIDENCE for component in circuit.components)
    assert [sub.id for sub in circuit.subcircuits] == ["prep", "infer"]
    assert circuit.subcircuits[1].component_ids == ("encode", "score")


def test_derived_circuit_validates_clean() -> None:
    circuit = methodology_to_circuit(make_methodology(), source_id="paper-x")

    assert circuit is not None
    report = validate_diagram(circuit)
    assert report.errors == ()
    assert report.warnings == ()


def test_derived_circuit_without_figure_carries_no_fake_evidence() -> None:
    circuit = methodology_to_circuit(make_methodology(with_figure=False), source_id="paper-x")

    assert circuit is not None
    assert all(component.evidence is None for component in circuit.components)
    assert circuit.source.figure_id == "derived-paper-x"
    assert circuit.source.page == 1


def test_derived_circuit_drops_dangling_edges() -> None:
    methodology = make_methodology().model_copy(
        update={
            "edges": (
                MethodologyEdge(from_node="raw", to="ghost"),
                MethodologyEdge(from_node="ghost", to="encode"),
            )
        }
    )
    circuit = methodology_to_circuit(methodology, source_id="paper-x")

    assert circuit is not None
    assert [net.id for net in circuit.nets] == ["solo0", "solo1", "solo2", "solo3"]
    assert validate_diagram(circuit).errors == ()


def test_derived_structure_maps_groups_to_modules_and_steps_to_parts() -> None:
    structure = methodology_to_structure(make_methodology())

    assert structure is not None
    assert structure.title == "Toy pipeline (system structure)"
    assert structure.root.id == "system"
    assert [child.id for child in structure.root.children] == ["g-prep", "g-infer", "n-loner"]
    infer = structure.root.children[1]
    assert [part.id for part in infer.children] == ["n-encode", "n-score"]
    assert infer.children[0].part == "model"
    assert structure.root.confidence == DERIVED_CONFIDENCE
    assert "methodology flow" in (structure.root.evidence.quote or "")


def test_derived_structure_validates_clean() -> None:
    structure = methodology_to_structure(make_methodology())

    assert structure is not None
    report = validate_diagram(structure)
    assert report.errors == ()
    assert report.warnings == ()


def test_derivation_returns_none_without_steps() -> None:
    empty = MethodologyIR(version=1, title="Empty", groups=(), nodes=(), edges=())

    assert methodology_to_circuit(empty, source_id="paper-x") is None
    assert methodology_to_structure(empty) is None


@pytest.mark.parametrize("derived", ["circuit", "structure"])
def test_derived_labels_survive_long_text(derived: str) -> None:
    long_label = "L" * 512
    methodology = MethodologyIR(
        version=1,
        title="T" * 512,
        groups=(),
        nodes=(
            MethodologyNode(
                id="only",
                label=long_label,
                kind=MethodologyNodeKind.PROCESS,
                confidence=0.5,
            ),
        ),
        edges=(),
    )

    if derived == "circuit":
        result = methodology_to_circuit(methodology, source_id="paper-x")
        assert result is not None
        assert len(result.title) <= 512
        assert len(result.components[0].label) <= 256
        assert validate_diagram(result).errors == ()
    else:
        result = methodology_to_structure(methodology)
        assert result is not None
        assert len(result.title) <= 512
        assert validate_diagram(result).errors == ()
