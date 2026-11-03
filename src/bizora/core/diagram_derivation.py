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

import re

from bizora.contracts.diagram_ir import (
    BlockKind,
    CircuitComponent,
    CircuitEvidence,
    CircuitIR,
    CircuitNet,
    CircuitPort,
    CircuitSource,
    ComponentType,
    MethodologyEdge,
    MethodologyGroup,
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


#: Methodology step kinds with a real 3D shape keep their kind as
#: the derived component type; abstract steps stay generic blocks.
_DERIVED_COMPONENT_TYPES = {
    "model": ComponentType.MODEL,
    "store": ComponentType.STORE,
    "dataset": ComponentType.DATASET,
    "input": ComponentType.INPUT,
    "output": ComponentType.OUTPUT,
    "decision": ComponentType.DECISION,
    "process": ComponentType.PROCESS,
    "evaluation": ComponentType.EVALUATION,
}


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
                type=_DERIVED_COMPONENT_TYPES.get(node.kind.value, ComponentType.BLOCK),
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

#: A transcribed figure flow below this many steps rarely covers a full
#: paper method, so the pipeline enriches it with text-stated steps.
#: Richer figures are served exactly as drawn (no extra model call).
ENRICH_THIN_NODES = 12

#: Text steps at least this similar (label token Jaccard) to a figure
#: step are the same step restated, not a new one.
MERGE_MATCH_SIMILARITY = 0.5


def _label_tokens(label: str) -> frozenset[str]:
    """Lowercase alphanumeric words of a step label."""
    return frozenset(re.findall(r"[a-z0-9]+", label.lower()))


def _label_similarity(left: str, right: str) -> float:
    """Token-set Jaccard similarity of two step labels (0 when either is empty)."""
    tokens_left, tokens_right = _label_tokens(left), _label_tokens(right)
    if not tokens_left or not tokens_right:
        return 0.0
    return len(tokens_left & tokens_right) / len(tokens_left | tokens_right)


def _fresh_id(want: str, used: set[str]) -> str:
    """An id based on want that is not in used (text- prefix, then counter)."""
    candidate = _truncate(want, 128)
    if candidate not in used:
        used.add(candidate)
        return candidate
    candidate = _truncate(f"text-{want}", 128)
    if candidate not in used:
        used.add(candidate)
        return candidate
    counter = 2
    while _truncate(f"{candidate}-{counter}", 128) in used:
        counter += 1
    candidate = _truncate(f"{candidate}-{counter}", 128)
    used.add(candidate)
    return candidate


def merge_methodology_text(
    figure: MethodologyIR, text: MethodologyIR
) -> MethodologyIR | None:
    """Enrich a transcribed figure flow with text-stated steps.

    The figure stays the base: its nodes, edges, groups, and title are
    kept verbatim, and every added step carries its own page/quote
    evidence, so the UI can tell drawn steps from text ones. Text steps
    that restate a figure step (label similarity at or above
    MERGE_MATCH_SIMILARITY) map onto it instead of duplicating it, and
    text edges resolve through that mapping, so added steps connect to
    the drawn flow instead of floating beside it. Returns None when the
    text adds no node or edge.
    """
    used_ids = {node.id for node in figure.nodes}
    id_map: dict[str, str] = {}
    added: list[tuple[str, str]] = []  # (text id, merged id)
    for node in text.nodes:
        best_id: str | None = None
        best_similarity = 0.0
        for figure_node in figure.nodes:
            similarity = _label_similarity(node.label, figure_node.label)
            if similarity > best_similarity:
                best_id, best_similarity = figure_node.id, similarity
        if best_id is not None and best_similarity >= MERGE_MATCH_SIMILARITY:
            id_map[node.id] = best_id
            continue
        merged_id = _fresh_id(node.id, used_ids)
        id_map[node.id] = merged_id
        added.append((node.id, merged_id))

    figure_group_labels = {group.id: group.label for group in figure.groups}
    used_group_ids = set(figure_group_labels)
    text_groups = {group.id: group for group in text.groups}
    group_map: dict[str, str] = {}
    merged_groups = list(figure.groups)
    for group in text.groups:
        if figure_group_labels.get(group.id) == group.label:
            group_map[group.id] = group.id
            continue
        merged_id = _fresh_id(group.id, used_group_ids)
        group_map[group.id] = merged_id
        parent = group.parent if group.parent in text_groups else None
        merged_groups.append(
            MethodologyGroup(
                id=merged_id,
                label=_truncate(group.label, 256),
                parent=group_map.get(parent, parent) if parent else None,
            )
        )
    # Remap pass: parents resolve to merged ids (groups iterate in text
    # order, so a parent usually maps before its child; orphans drop).
    remapped_groups = list(figure.groups)
    for group in merged_groups[len(figure.groups) :]:
        parent = group.parent
        remapped_groups.append(
            group
            if parent is None or parent in used_group_ids
            else group.model_copy(update={"parent": None})
        )

    text_nodes = {node.id: node for node in text.nodes}
    merged_nodes = list(figure.nodes)
    for text_id, merged_id in added:
        node = text_nodes[text_id]
        node_group = group_map.get(node.group, node.group) if node.group else None
        merged_nodes.append(
            node.model_copy(
                update={
                    "id": merged_id,
                    "group": node_group
                    if node_group in used_group_ids
                    else None,
                }
            )
        )

    existing_edges = {
        (edge.from_node, edge.to, edge.kind) for edge in figure.edges
    }
    merged_edges = list(figure.edges)
    for edge in text.edges:
        resolved_from = id_map.get(edge.from_node)
        resolved_to = id_map.get(edge.to)
        if resolved_from is None or resolved_to is None:
            continue
        if resolved_from == resolved_to:
            continue
        key = (resolved_from, resolved_to, edge.kind)
        if key in existing_edges:
            continue
        existing_edges.add(key)
        merged_edges.append(
            MethodologyEdge(
                from_node=resolved_from,
                to=resolved_to,
                label=edge.label,
                kind=edge.kind,
            )
        )

    if len(merged_nodes) == len(figure.nodes) and len(merged_edges) == len(
        figure.edges
    ):
        return None
    return MethodologyIR(
        version=1,
        title=figure.title,
        groups=tuple(remapped_groups),
        nodes=tuple(merged_nodes),
        edges=tuple(merged_edges),
    )


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


def first_array_cell(structure: StructureIR) -> StructureBlock | None:
    """Return the first array's repeated cell, or None when absent.

    Walks the whole tree (arrays nest under chips and boards); the
    repeated cell is the array's first child of kind cell.
    """
    stack = [structure.root]
    while stack:
        block = stack.pop()
        if block.kind == BlockKind.ARRAY:
            for child in block.children:
                if child.kind == BlockKind.CELL:
                    return child
            return None
        stack.extend(reversed(block.children))
    return None


def _graft_children(block: StructureBlock, cell_id: str, children: tuple[StructureBlock, ...]) -> StructureBlock:
    """Return a copy of block with cell_id's children replaced."""
    if block.id == cell_id:
        return block.model_copy(update={"children": children})
    if not block.children:
        return block
    rebuilt = tuple(
        _graft_children(child, cell_id, children) for child in block.children
    )
    if rebuilt == block.children:
        return block
    return block.model_copy(update={"children": rebuilt})


def graft_cell_interior(
    figure_structure: StructureIR, text_structure: StructureIR
) -> StructureIR | None:
    """Graft text-stated cell devices into a bare figure cell.

    A die photo often shows the array but not what is inside one
    cell, while the paper text names the cell's devices ("two pairs
    of NMOS transistors"). When the figure's repeated cell has no
    children and the text's repeated cell does, the text children —
    with their own page/quote evidence — become the figure cell's
    children, so the Cell interior view has something honest to show.
    Returns None when no graft applies (figure cell already detailed
    or text cell bare). Pure structural merge: first array's first
    cell on both sides, no label matching.
    """
    figure_cell = first_array_cell(figure_structure)
    if figure_cell is None or figure_cell.children:
        return None
    text_cell = first_array_cell(text_structure)
    if text_cell is None or not text_cell.children:
        return None
    root = _graft_children(figure_structure.root, figure_cell.id, text_cell.children)
    return figure_structure.model_copy(update={"root": root})
