"""Bill-of-materials extraction from methodology graphs.

Nodes are grouped into BOM lines by their label plus a signature of
config values. Which config keys form the signature is data
(:data:`SIGNATURE_KEYS`); the logic never branches on part names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bizora.contracts.graph import MethodologyGraph
from bizora.packs.electronics.netlist import ELEMENT_TABLE, KIND_KEY, REFDES_KEY

# ---------------------------------------------------------------------------
# BOM data: signature keys and kinds excluded from the parts list.
# ---------------------------------------------------------------------------

SIGNATURE_KEYS: tuple[str, ...] = (
    "value",
    "resistance_ohm",
    "capacitance_f",
    "inductance_h",
    "voltage_v",
    "current_a",
    "package",
    "part_number",
    "model",
    "subckt",
)

EXCLUDED_KINDS: tuple[str, ...] = ("directive",)

DISPLAY_KEYS: tuple[str, ...] = ("value", "package", "part_number")


@dataclass(frozen=True)
class BomEntry:
    """One aggregated BOM line."""

    designators: tuple[str, ...]
    label: str
    quantity: int
    attributes: dict[str, str]


@dataclass(frozen=True)
class BomResult:
    """One extracted bill of materials."""

    entries: tuple[BomEntry, ...]
    total_quantity: int
    warnings: tuple[str, ...]


def _signature_text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def extract_bom(
    graph: MethodologyGraph,
    refdes_by_node: Mapping[str, str] | None = None,
) -> BomResult:
    """Aggregate simulatable graph nodes into BOM lines.

    ``refdes_by_node`` (from netlist extraction) keeps designators
    consistent; when absent, stable ``P<n>`` designators are assigned.
    """
    groups: dict[tuple[str, tuple[tuple[str, str], ...]], list[str]] = {}
    labels: dict[tuple[str, tuple[tuple[str, str], ...]], str] = {}
    attributes: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, str]] = {}
    warnings: list[str] = []
    auto_index = 0

    for node in graph.nodes:
        raw_kind = node.config.get(KIND_KEY)
        kind = raw_kind if isinstance(raw_kind, str) else None
        if kind is None or kind not in ELEMENT_TABLE or kind in EXCLUDED_KINDS:
            continue
        refdes: str | None = None
        if refdes_by_node is not None:
            refdes = refdes_by_node.get(node.id)
        if refdes is None:
            raw_refdes = node.config.get(REFDES_KEY)
            if isinstance(raw_refdes, str) and raw_refdes.strip():
                refdes = raw_refdes.strip()
        if refdes is None:
            auto_index += 1
            refdes = f"P{auto_index}"
            warnings.append(f"node '{node.id}': no refdes; assigned '{refdes}'")
        signature: list[tuple[str, str]] = []
        for key in SIGNATURE_KEYS:
            text = _signature_text(node.config.get(key))
            if text is not None:
                signature.append((key, text))
        group_key = (node.label.strip().lower(), tuple(signature))
        groups.setdefault(group_key, []).append(refdes)
        labels.setdefault(group_key, node.label)
        attributes.setdefault(
            group_key, {key: text for key, text in signature if key in DISPLAY_KEYS}
        )

    entries = tuple(
        BomEntry(
            designators=tuple(sorted(designators)),
            label=labels[key],
            quantity=len(designators),
            attributes=dict(attributes[key]),
        )
        for key, designators in sorted(groups.items(), key=lambda item: sorted(item[1]))
    )
    return BomResult(
        entries=entries,
        total_quantity=sum(entry.quantity for entry in entries),
        warnings=tuple(warnings),
    )
