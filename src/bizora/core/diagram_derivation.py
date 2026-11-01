"""Deterministic methodology-derived diagrams.

When a paper has no circuit figure or physical structure to transcribe,
the methodology flow still describes a system: derive a block-level
schematic (one block per step, one signal net per edge) and a 3D
structure (groups to modules, steps to parts) from it. Pure functions
of the MethodologyIR — no provider calls, no domain knowledge, no
paper-specific constants. Derived elements carry low confidence and
honest evidence quotes so the UI labels them assumed, never
from-paper.
"""

from bizora.contracts.diagram_ir import (
    BlockKind,
    CircuitComponent,
    CircuitEvidence,
    CircuitIR,
    CircuitNet,
    CircuitPort,
    CircuitSource,
    ComponentType,
    MethodologyIR,
    MethodologyNodeKind,
    NetRole,
    PortDirection,
    Side,
    StructureBlock,
    StructureEvidence,
    StructureIR,
    SubCircuit,
)

#: Confidence for derived elements: below the assumed threshold, so the
#: UI never presents a derivation as paper evidence.
DERIVED_CONFIDENCE = 0.4


def _truncate(value: str, limit: int) -> str:
    """Clip a string to a contract length limit."""
    return value[:limit] if len(value) > limit else value


def _methodology_figure(methodology: MethodologyIR) -> tuple[str | None, int | None]:
    """First figure reference carried by the methodology's own evidence."""
    figure_id: str | None = None
    page: int | None = None
    for node in methodology.nodes:
        if node.evidence is None:
            continue
        if figure_id is None and node.evidence.figure_id:
            figure_id = node.evidence.figure_id
        if page is None and node.evidence.page is not None:
            page = node.evidence.page
        if figure_id is not None and page is not None:
            break
    return (figure_id, page)


def methodology_to_circuit(
    methodology: MethodologyIR, *, source_id: str
) -> CircuitIR | None:
    """Derive a block-level schematic from a methodology flow.

    Returns None when the methodology has no steps: with nothing to
    derive from, an empty schematic would be noise. The result
    validates clean: edge nets always join two pins, and isolated
    steps get a ported solo net each.
    """
    if not methodology.nodes:
        return None
    figure_id, page = _methodology_figure(methodology)
    by_id = {node.id: node for node in methodology.nodes}
    edges = [
        (index, edge)
        for index, edge in enumerate(methodology.edges)
        if edge.from_node in by_id and edge.to in by_id
    ]
    incoming: dict[str, list[int]] = {node.id: [] for node in methodology.nodes}
    outgoing: dict[str, list[int]] = {node.id: [] for node in methodology.nodes}
    for position, (_, edge) in enumerate(edges):
        outgoing[edge.from_node].append(position)
        incoming[edge.to].append(position)

    nets: list[CircuitNet] = []
    for position, (_, edge) in enumerate(edges):
        label = edge.label or f"{edge.from_node} → {edge.to}"
        nets.append(
            CircuitNet(
                id=f"e{position}",
                label=_truncate(label, 256),
                role=NetRole.SIGNAL,
                is_global=False,
            )
        )

    ports: list[CircuitPort] = []
    components: list[CircuitComponent] = []
    solo_index = 0
    for node in methodology.nodes:
        pins: dict[str, str] = {}
        pin_sides: dict[str, Side] = {}
        for position in incoming[node.id]:
            pins[f"in{position if len(incoming[node.id]) > 1 else ''}"] = f"e{position}"
        for position in outgoing[node.id]:
            pins[f"out{position if len(outgoing[node.id]) > 1 else ''}"] = f"e{position}"
        for pin in pins:
            pin_sides[pin] = Side.LEFT if pin.startswith("in") else Side.RIGHT
        if not pins:
            net_id = f"solo{solo_index}"
            solo_index += 1
            nets.append(
                CircuitNet(
                    id=net_id,
                    label=_truncate(f"{node.label} I/O", 256),
                    role=NetRole.SIGNAL,
                    is_global=False,
                )
            )
            pins["io"] = net_id
            pin_sides["io"] = Side.RIGHT
            direction = PortDirection.INOUT
            side = Side.RIGHT
            if node.kind is MethodologyNodeKind.INPUT:
                direction = PortDirection.IN
                side = Side.LEFT
            elif node.kind is MethodologyNodeKind.OUTPUT:
                direction = PortDirection.OUT
            ports.append(
                CircuitPort(
                    id=_truncate(f"port_{node.id}", 128),
                    net=net_id,
                    label=_truncate(node.label, 256),
                    dir=direction,
                    side=side,
                )
            )
        evidence = (
            CircuitEvidence(
                figure_id=figure_id,
                quote=f"Derived from methodology step '{node.label}'.",
            )
            if figure_id is not None
            else None
        )
        components.append(
            CircuitComponent(
                id=node.id,
                label=_truncate(node.label, 256),
                type=ComponentType.BLOCK,
                pins=pins,
                pin_sides=pin_sides,
                confidence=DERIVED_CONFIDENCE,
                evidence=evidence,
            )
        )

    subcircuits = [
        SubCircuit(
            id=_truncate(group.id, 128),
            label=_truncate(group.label, 256),
            component_ids=tuple(
                node.id for node in methodology.nodes if node.group == group.id
            ),
        )
        for group in methodology.groups
    ]
    subcircuits = [sub for sub in subcircuits if sub.component_ids]

    return CircuitIR(
        version=1,
        title=_truncate(f"{methodology.title} (system blocks)", 512),
        source=CircuitSource(
            figure_id=figure_id or _truncate(f"derived-{source_id}", 128),
            page=page or 1,
        ),
        components=tuple(components),
        nets=tuple(nets),
        ports=tuple(ports),
        subcircuits=tuple(subcircuits),
    )


def methodology_to_structure(methodology: MethodologyIR) -> StructureIR | None:
    """Derive a 3D structure from a methodology flow.

    Groups become modules and steps become parts, so every paper gets
    an explorable structure even when it states no physical layout.
    Returns None when the methodology has no steps.
    """
    if not methodology.nodes:
        return None
    figure_id, page = _methodology_figure(methodology)

    def evidence_for(label: str) -> StructureEvidence:
        """Honest derivation evidence for one block."""
        return StructureEvidence(
            page=page,
            figure_id=figure_id,
            quote=f"Derived from methodology step '{label}'.",
        )

    def part_for(node_id: str, label: str, kind: str) -> StructureBlock:
        """One part block for one methodology step."""
        return StructureBlock(
            id=_truncate(f"n-{node_id}", 128),
            label=_truncate(label, 512),
            kind=BlockKind.PART,
            part=_truncate(kind, 128),
            confidence=DERIVED_CONFIDENCE,
            evidence=evidence_for(label),
        )

    grouped = {node.group for node in methodology.nodes if node.group}
    modules: list[StructureBlock] = []
    for group in methodology.groups:
        members = [node for node in methodology.nodes if node.group == group.id]
        if not members:
            continue
        grouped.discard(group.id)
        modules.append(
            StructureBlock(
                id=_truncate(f"g-{group.id}", 128),
                label=_truncate(group.label, 512),
                kind=BlockKind.MODULE,
                confidence=DERIVED_CONFIDENCE,
                evidence=evidence_for(group.label),
                children=tuple(
                    part_for(node.id, node.label, node.kind.value) for node in members
                ),
            )
        )
    ungrouped = [
        part_for(node.id, node.label, node.kind.value)
        for node in methodology.nodes
        if node.group is None or node.group in grouped
    ]
    root = StructureBlock(
        id="system",
        label=_truncate(methodology.title, 512),
        kind=BlockKind.MODULE,
        confidence=DERIVED_CONFIDENCE,
        evidence=StructureEvidence(
            page=page,
            figure_id=figure_id,
            quote="Derived from the methodology flow.",
        ),
        children=tuple(modules + ungrouped),
    )
    return StructureIR(
        version=1,
        title=_truncate(f"{methodology.title} (system structure)", 512),
        root=root,
    )


#: Engine minimum: buildStructureSafe refuses scenes with fewer than two
#: boxes ("no physical structure could be built from this IR").
ENGINE_MIN_BOXES = 2


def structure_drawable_boxes(structure: StructureIR) -> int:
    """Count the boxes the engine would draw for a structure IR.

    Mirrors buildStructureScene's three paths (array / layer-row / grid)
    so the pipeline can tell a drawable transcription from a degenerate
    one before serving it. Pure shape math over the IR: no domain
    knowledge, no paper-specific constants.
    """
    root = structure.root
    kids = root.children
    array = next((kid for kid in kids if kid.kind == BlockKind.ARRAY), None)
    if array is not None:
        rows, cols = (1, 1)
        if isinstance(array.count, int):
            rows, cols = (1, array.count)
        elif array.count is not None:
            rows, cols = (array.count.rows, array.count.cols)
        return 1 + rows * cols + (len(kids) - 1)
    if kids and all(kid.tensor_shape or kid.kind == BlockKind.LAYER for kid in kids):
        return 1 + len(kids)
    plate = 1 if root.kind in (
        BlockKind.CHIP,
        BlockKind.BOARD,
        BlockKind.MODULE,
        BlockKind.REGION,
    ) else 0
    return plate + len(kids)
