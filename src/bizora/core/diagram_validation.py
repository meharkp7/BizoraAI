"""Semantic validators for diagram IRs.

Shape checks live in bizora.contracts.diagram_ir; these validators check
cross-references and domain rules, collecting every problem instead of
failing fast so the extraction repair loop sees them all at once.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from bizora.contracts.diagram_ir import (
    ArrayCount,
    BlockKind,
    BlockPosition,
    CircuitIR,
    ComponentType,
    MethodologyIR,
    NetRole,
    StructureBlock,
    StructureIR,
)

REQUIRED_PINS: dict[ComponentType, frozenset[str]] = {
    ComponentType.NMOS: frozenset({"d", "g", "s"}),
    ComponentType.PMOS: frozenset({"d", "g", "s"}),
    ComponentType.RESISTOR: frozenset({"a", "b"}),
    ComponentType.CAPACITOR: frozenset({"a", "b"}),
    ComponentType.INDUCTOR: frozenset({"a", "b"}),
    ComponentType.DIODE: frozenset({"a", "k"}),
    ComponentType.VSOURCE: frozenset({"p", "n"}),
    ComponentType.ISOURCE: frozenset({"p", "n"}),
    ComponentType.GROUND: frozenset({"g"}),
    ComponentType.INVERTER: frozenset({"in", "out"}),
    ComponentType.BUFFER: frozenset({"in", "out"}),
    ComponentType.AMP: frozenset({"inp", "inn", "out"}),
    ComponentType.COMPARATOR: frozenset({"inp", "inn", "out"}),
}

OPTIONAL_PINS: dict[ComponentType, frozenset[str]] = {
    ComponentType.NMOS: frozenset({"b"}),
    ComponentType.PMOS: frozenset({"b"}),
}

DANGLING_CHECK_ROLES = frozenset(
    {NetRole.SIGNAL, NetRole.CLOCK, NetRole.INPUT, NetRole.OUTPUT}
)


@dataclass(frozen=True)
class DiagramValidationResult:
    """Outcome of validating one IR: errors, warnings, and count stats."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    stats: Mapping[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _duplicates(ids: list[str]) -> list[str]:
    counts = Counter(ids)
    return sorted(id_ for id_, count in counts.items() if count > 1)


def validate_circuit(ir: CircuitIR) -> DiagramValidationResult:
    """Validate component/net/port references and schematic rules."""
    errors: list[str] = []
    warnings: list[str] = []

    for dup in _duplicates([c.id for c in ir.components]):
        errors.append(f"duplicate component id '{dup}'")
    for dup in _duplicates([n.id for n in ir.nets]):
        errors.append(f"duplicate net id '{dup}'")
    for dup in _duplicates([p.id for p in ir.ports]):
        errors.append(f"duplicate port id '{dup}'")
    for dup in _duplicates([s.id for s in ir.subcircuits]):
        errors.append(f"duplicate subcircuit id '{dup}'")

    net_ids = {net.id for net in ir.nets}
    component_ids = {component.id for component in ir.components}

    for component in ir.components:
        required = REQUIRED_PINS.get(component.type)
        if required is None:  # block: any pins allowed
            if not component.pins:
                warnings.append(f"component '{component.id}' (block) has no pins")
        else:
            for pin in sorted(required):
                if pin not in component.pins:
                    errors.append(
                        f"component '{component.id}' ({component.type.value}) "
                        f"missing required pin '{pin}'"
                    )
            allowed = required | OPTIONAL_PINS.get(component.type, frozenset())
            for pin in sorted(component.pins):
                if pin not in allowed:
                    warnings.append(
                        f"component '{component.id}' ({component.type.value}) "
                        f"has unexpected pin '{pin}'"
                    )
        for pin, net_ref in sorted(component.pins.items()):
            if not net_ref.strip():
                errors.append(
                    f"component '{component.id}' pin '{pin}' is floating "
                    "(empty net reference)"
                )
            elif net_ref not in net_ids:
                errors.append(
                    f"component '{component.id}' pin '{pin}' "
                    f"references unknown net '{net_ref}'"
                )
        if component.pin_sides is not None:
            if component.type is not ComponentType.BLOCK:
                warnings.append(
                    f"component '{component.id}' ({component.type.value}) "
                    "defines pin_sides, which only applies to block components"
                )
            for pin in sorted(component.pin_sides):
                if pin not in component.pins:
                    warnings.append(
                        f"component '{component.id}' pin_sides entry '{pin}' "
                        "has no matching pin"
                    )

    for port in ir.ports:
        if port.net not in net_ids:
            errors.append(
                f"port '{port.id}' references unknown net '{port.net}'"
            )

    for subcircuit in ir.subcircuits:
        for component_id in subcircuit.component_ids:
            if component_id not in component_ids:
                errors.append(
                    f"subcircuit '{subcircuit.id}' references "
                    f"unknown component '{component_id}'"
                )

    connections: dict[str, int] = {net.id: 0 for net in ir.nets}
    ported: set[str] = set()
    for component in ir.components:
        for net_id in component.pins.values():
            if net_id in connections:
                connections[net_id] += 1
    for port in ir.ports:
        if port.net in connections:
            connections[port.net] += 1
            ported.add(port.net)

    for net in ir.nets:
        count = connections[net.id]
        if net.role in DANGLING_CHECK_ROLES:
            if count < 2 and not net.is_global and net.id not in ported:
                errors.append(
                    f"net '{net.id}' ({net.role.value}) has only "
                    f"{count} connection{'s' if count != 1 else ''}"
                )
        elif count == 0:
            warnings.append(f"net '{net.id}' ({net.role.value}) is unused")

    if not any(net.role in (NetRole.SUPPLY, NetRole.GROUND) for net in ir.nets):
        errors.append("circuit has no supply or ground net")

    stats = {
        "components": len(ir.components),
        "nets": len(ir.nets),
        "ports": len(ir.ports),
        "connections": sum(connections.values()),
        "subcircuits": len(ir.subcircuits),
    }
    return DiagramValidationResult(
        errors=tuple(errors), warnings=tuple(warnings), stats=stats
    )


def validate_methodology(ir: MethodologyIR) -> DiagramValidationResult:
    """Validate node/edge/group references and flow rules."""
    errors: list[str] = []
    warnings: list[str] = []

    for dup in _duplicates([g.id for g in ir.groups]):
        errors.append(f"duplicate group id '{dup}'")
    for dup in _duplicates([n.id for n in ir.nodes]):
        errors.append(f"duplicate node id '{dup}'")

    group_ids = {group.id for group in ir.groups}
    node_ids = {node.id for node in ir.nodes}

    for group in ir.groups:
        if group.parent is not None and group.parent not in group_ids:
            errors.append(
                f"group '{group.id}' references unknown parent group "
                f"'{group.parent}'"
            )

    for node in ir.nodes:
        if node.group is not None and node.group not in group_ids:
            errors.append(
                f"node '{node.id}' references unknown group '{node.group}'"
            )

    for edge in ir.edges:
        if edge.from_node not in node_ids:
            errors.append(
                f"edge {edge.from_node}->{edge.to} references "
                f"unknown node '{edge.from_node}'"
            )
        if edge.to not in node_ids:
            errors.append(
                f"edge {edge.from_node}->{edge.to} references "
                f"unknown node '{edge.to}'"
            )

    touched: set[str] = set()
    for edge in ir.edges:
        touched.add(edge.from_node)
        touched.add(edge.to)
    orphans = sorted(node.id for node in ir.nodes if node.id not in touched)
    for node_id in orphans:
        warnings.append(f"node '{node_id}' is orphaned (no edges)")

    stats = {
        "groups": len(ir.groups),
        "nodes": len(ir.nodes),
        "edges": len(ir.edges),
        "orphans": len(orphans),
    }
    return DiagramValidationResult(
        errors=tuple(errors), warnings=tuple(warnings), stats=stats
    )


def _walk_blocks(root: StructureBlock) -> list[tuple[StructureBlock, int]]:
    """Return (block, depth) pairs in tree order with the root at depth 0."""
    ordered: list[tuple[StructureBlock, int]] = []
    stack: list[tuple[StructureBlock, int]] = [(root, 0)]
    while stack:
        block, depth = stack.pop()
        ordered.append((block, depth))
        for child in reversed(block.children):
            stack.append((child, depth + 1))
    return ordered


def validate_structure(ir: StructureIR) -> DiagramValidationResult:
    """Validate counts, array children, and dimensions of a structure tree."""
    errors: list[str] = []
    warnings: list[str] = []
    _ = warnings

    walked = _walk_blocks(ir.root)
    arrays = 0
    for block, _depth in walked:
        if block.kind == "array":
            arrays += 1
            if not block.children:
                errors.append(
                    f"block '{block.id}' is an array with no repeated cell child"
                )
        count = block.count
        if count is not None:
            if isinstance(count, ArrayCount):
                if count.rows < 1:
                    errors.append(
                        f"block '{block.id}' array rows must be >= 1, "
                        f"got {count.rows}"
                    )
                if count.cols < 1:
                    errors.append(
                        f"block '{block.id}' array cols must be >= 1, "
                        f"got {count.cols}"
                    )
            elif count < 1:
                errors.append(
                    f"block '{block.id}' count must be >= 1, got {count}"
                )
        if block.dims is not None:
            for name, value in (
                ("w", block.dims.w),
                ("h", block.dims.h),
                ("d", block.dims.d),
            ):
                if value is not None and not value > 0:
                    errors.append(
                        f"block '{block.id}' dims.{name} must be > 0, got {value}"
                    )

    root = ir.root
    if root.kind == "array" and not isinstance(root.count, ArrayCount):
        others = [
            child
            for child in root.children
            if child.kind not in ("cell", "part")
        ]
        if not others:
            count_note = (
                f"count {root.count}" if root.count is not None else "no count"
            )
            errors.append(
                f"block '{root.id}' is an array root without a rows/cols "
                f"grid and no other blocks: {count_note} alone "
                "cannot render"
            )

    stats = {
        "blocks": len(walked),
        "max_depth": max((depth for _, depth in walked), default=0),
        "arrays": arrays,
    }
    return DiagramValidationResult(
        errors=tuple(errors), warnings=tuple(warnings), stats=stats
    )


_ARRANGE_SIDES: tuple[BlockPosition, ...] = (
    BlockPosition.BOTTOM,
    BlockPosition.RIGHT,
    BlockPosition.LEFT,
    BlockPosition.TOP,
)


def normalize_structure_layout(
    ir: StructureIR,
) -> tuple[StructureIR, tuple[str, ...]]:
    """Arrange one structure tree for the renderer without changing content.

    The scene builder draws the first root-level array as the main field
    and every other root block as a side strip: non-cell children nested
    under an array never render, and side strips without a position all
    collapse onto the same edge. So shared blocks nested under an array
    move to the root (nothing else about them changes) and unplaced root
    blocks take distinct illustrative sides. Every adjustment is reported
    in the returned notes, which the endpoint surfaces as warnings.
    """
    notes: list[str] = []
    hoisted: list[StructureBlock] = []

    def arrange(block: StructureBlock, *, is_root: bool) -> StructureBlock:
        kids = tuple(arrange(child, is_root=False) for child in block.children)
        if (
            not is_root
            and block.kind == BlockKind.ARRAY
            and any(child.kind == BlockKind.CELL for child in kids)
        ):
            kept = tuple(c for c in kids if c.kind == BlockKind.CELL)
            rest = [c for c in kids if c.kind != BlockKind.CELL]
            for extra in rest:
                notes.append(
                    f"block '{extra.id}' nested under array '{block.id}' "
                    "cannot render there; shown at chip level."
                )
            hoisted.extend(rest)
            kids = kept
        if kids != block.children:
            return block.model_copy(update={"children": kids})
        return block

    root = arrange(ir.root, is_root=True)
    kids = tuple(root.children) + tuple(hoisted)
    main = next((c for c in kids if c.kind == BlockKind.ARRAY), None)
    taken = {c.pos for c in kids if c.pos is not None}
    cycle = [side for side in _ARRANGE_SIDES if side not in taken]
    need = [
        index
        for index, child in enumerate(kids)
        if child is not main
        and child.kind != BlockKind.CELL
        and child.pos is None
    ]
    if need:
        updated = list(kids)
        names: list[str] = []
        for order, index in enumerate(need):
            pool = cycle or list(_ARRANGE_SIDES)
            side = pool[order % len(pool)]
            updated[index] = kids[index].model_copy(update={"pos": side})
            names.append(f"'{kids[index].id}'")
        kids = tuple(updated)
        notes.append(
            f"arrangement of {', '.join(names)} not stated; "
            "placed illustratively."
        )
    if kids != root.children or hoisted:
        root = root.model_copy(update={"children": kids})
    arranged = ir.model_copy(update={"root": root})
    return arranged, tuple(notes)


def validate_diagram(
    ir: CircuitIR | MethodologyIR | StructureIR,
) -> DiagramValidationResult:
    """Dispatch to the validator matching the IR type."""
    if isinstance(ir, CircuitIR):
        return validate_circuit(ir)
    if isinstance(ir, MethodologyIR):
        return validate_methodology(ir)
    if isinstance(ir, StructureIR):
        return validate_structure(ir)
    raise TypeError(f"unsupported IR type: {type(ir).__name__}")
