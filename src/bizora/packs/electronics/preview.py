"""Simulation preview for the electronics pack: netlist, BOM, findings.

The builder only formats the outputs of netlist extraction, BOM
aggregation, and electrical preflight into one human-readable preview.
Graphs without simulatable nodes get no preview (None) so callers can
fall back to explore-only mode.
"""

from __future__ import annotations

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.packs import SimulationPreview, SimulationPreviewSection
from bizora.packs.electronics.bom import extract_bom
from bizora.packs.electronics.netlist import extract_netlist, simulatable_nodes
from bizora.packs.electronics.preflight import preflight_graph

PACK_ID = "electronics"
TITLE = "SPICE circuit preview"
MAX_WARNING_CHARS = 500


def build_preview(graph: MethodologyGraph) -> SimulationPreview | None:
    """Return the netlist/BOM/findings preview, or None when not simulatable."""
    if not simulatable_nodes(graph):
        return None
    netlist = extract_netlist(graph)
    bom = extract_bom(graph, netlist.refdes_by_node)
    findings = preflight_graph(graph)
    netlist_lines = (
        list(netlist.element_lines)
        + list(netlist.model_lines)
        + list(netlist.directive_lines)
    )
    bom_lines = [
        f"{', '.join(entry.designators)}: {entry.label} x{entry.quantity}"
        + (
            f" ({', '.join(f'{key}={value}' for key, value in sorted(entry.attributes.items()))})"
            if entry.attributes
            else ""
        )
        for entry in bom.entries
    ]
    warnings = (
        [warning[:MAX_WARNING_CHARS] for warning in netlist.warnings]
        + [warning[:MAX_WARNING_CHARS] for warning in bom.warnings]
        + [
            f"{finding.severity.value.upper()}: {finding.rule_id}: {finding.message}"[
                :MAX_WARNING_CHARS
            ]
            for finding in findings
        ]
    )
    return SimulationPreview(
        pack_id=PACK_ID,
        title=TITLE,
        sections=(
            SimulationPreviewSection(heading="Netlist", lines=tuple(netlist_lines)),
            SimulationPreviewSection(
                heading=(
                    f"Bill of materials ({bom.total_quantity} part)"
                    if bom.total_quantity == 1
                    else f"Bill of materials ({bom.total_quantity} parts)"
                ),
                lines=tuple(bom_lines),
            ),
        ),
        warnings=tuple(warnings),
    )
