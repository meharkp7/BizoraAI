"""Tests for deterministic methodology-derived diagrams."""

import pytest

from bizora.contracts.diagram_ir import (
    ArrayCount,
    BlockKind,
    ComponentType,
    MethodologyEdge,
    MethodologyEvidence,
    MethodologyGroup,
    MethodologyIR,
    MethodologyNode,
    MethodologyNodeKind,
    StructureBlock,
    StructureEvidence,
    StructureIR,
)
from bizora.core.diagram_derivation import (
    DERIVED_CONFIDENCE,
    ENGINE_MIN_BOXES,
    first_array_cell,
    graft_cell_interior,
    methodology_to_circuit,
    methodology_to_structure,
    structure_drawable_boxes,
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


def make_block(kind: BlockKind, **overrides: object) -> StructureBlock:
    base: dict[str, object] = {
        "id": f"{kind.value}-1",
        "label": kind.value,
        "kind": kind,
        "confidence": 0.8,
        "children": (),
    }
    base.update(overrides)
    return StructureBlock.model_validate(base)


def test_drawable_boxes_mirrors_engine_paths() -> None:
    cell = make_block(BlockKind.CELL, id="cell")
    # Array-rooted transcription with a lone cell: grid path, no plate.
    lone = StructureIR(
        version=1,
        title="lone",
        root=make_block(BlockKind.ARRAY, id="root", children=(cell,)),
    )
    assert structure_drawable_boxes(lone) == 1
    assert structure_drawable_boxes(lone) < ENGINE_MIN_BOXES
    # Module frame with one part: plate plus the part.
    framed = StructureIR(
        version=1,
        title="framed",
        root=make_block(
            BlockKind.MODULE,
            id="root",
            children=(make_block(BlockKind.PART, id="p1"),),
        ),
    )
    assert structure_drawable_boxes(framed) == 2
    # Array child expands by rows x cols, plus plate and peripherals.
    arrayed = StructureIR(
        version=1,
        title="arrayed",
        root=make_block(
            BlockKind.CHIP,
            id="root",
            children=(
                make_block(
                    BlockKind.ARRAY,
                    id="arr",
                    count=ArrayCount(rows=8, cols=2),
                    children=(cell,),
                ),
                make_block(BlockKind.PERIPHERY, id="per"),
            ),
        ),
    )
    assert structure_drawable_boxes(arrayed) == 1 + 16 + 1
    # Layer rows draw a region plate plus every layer.
    layered = StructureIR(
        version=1,
        title="layered",
        root=make_block(
            BlockKind.REGION,
            id="root",
            children=tuple(
                make_block(BlockKind.LAYER, id=f"l{i}") for i in range(3)
            ),
        ),
    )
    assert structure_drawable_boxes(layered) == 4


def test_derived_structure_always_meets_engine_minimum() -> None:
    derived = methodology_to_structure(make_methodology())

    assert derived is not None
    assert structure_drawable_boxes(derived) >= ENGINE_MIN_BOXES


def make_array_structure(*, cell_children: tuple[StructureBlock, ...] = ()) -> StructureIR:
    """Chip -> array -> cell with the given cell children."""
    return StructureIR(
        version=1,
        title="macro",
        root=StructureBlock(
            id="chip",
            label="chip",
            kind=BlockKind.CHIP,
            confidence=0.9,
            children=(
                StructureBlock(
                    id="arr",
                    label="array",
                    kind=BlockKind.ARRAY,
                    count=ArrayCount(rows=16, cols=16),
                    confidence=0.8,
                    children=(
                        StructureBlock(
                            id="cell",
                            label="cell",
                            kind=BlockKind.CELL,
                            confidence=0.7,
                            children=cell_children,
                        ),
                    ),
                ),
            ),
        ),
    )


def make_device_pair() -> tuple[StructureBlock, ...]:
    """Two text-stated NMOS devices with page/quote evidence."""
    return (
        StructureBlock(
            id="nmos-a",
            label="NMOS pair N1-N2",
            kind=BlockKind.PART,
            part="nmos",
            confidence=0.75,
            evidence=StructureEvidence(page=3, quote="Two pairs of NMOS transistors."),
        ),
        StructureBlock(
            id="pmos-a",
            label="PMOS pull-up",
            kind=BlockKind.PART,
            part="pmos",
            confidence=0.7,
        ),
    )


def test_first_array_cell_finds_nested_cell() -> None:
    """The repeated cell is found under chip/array nesting."""
    cell = first_array_cell(make_array_structure())

    assert cell is not None
    assert cell.id == "cell"


def test_first_array_cell_absent_without_array() -> None:
    """Module/part trees have no repeated cell."""
    bare = StructureIR(
        version=1,
        title="system",
        root=StructureBlock(
            id="sys", label="sys", kind=BlockKind.MODULE, confidence=0.5
        ),
    )

    assert first_array_cell(bare) is None


def test_graft_cell_interior_merges_text_devices() -> None:
    """A bare figure cell gains the text cell's devices with evidence."""
    grafted = graft_cell_interior(
        make_array_structure(), make_array_structure(cell_children=make_device_pair())
    )

    assert grafted is not None
    cell = first_array_cell(grafted)
    assert cell is not None
    assert [child.id for child in cell.children] == ["nmos-a", "pmos-a"]
    assert cell.children[0].evidence is not None
    assert cell.children[0].evidence.page == 3
    assert grafted.root.id == "chip"
    assert validate_diagram(grafted).errors == ()


def test_graft_cell_interior_skips_detailed_figure_cell() -> None:
    """A figure cell with children is never overwritten."""
    detailed = make_array_structure(cell_children=make_device_pair())

    assert graft_cell_interior(detailed, detailed) is None


def test_graft_cell_interior_skips_bare_text_cell() -> None:
    """Nothing to graft when the text names no devices."""
    assert (
        graft_cell_interior(make_array_structure(), make_array_structure()) is None
    )
