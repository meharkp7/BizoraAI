"""Execute pack-provided copilot tools inside the core tool loop.

Packs declare tools as data (``copilot_tools``); this module converts
those declarations to provider specs and executes the two shapes the
lexical harness emits: ``{slug}_search_library`` over the pack's own
catalog entries and ``{slug}_preflight`` through the pack's own
``check_patch`` rules. A declared tool with no executor shape fails
loudly so the gap stays visible instead of silently unreachable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bizora.contracts.components import ComponentDetail
from bizora.contracts.packs import PackPreflightSeverity
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.component_service import build_replacement_node
from bizora.core.entity_registry import tokenize
from bizora.core.errors import BizoraError
from bizora.packs.base import DomainPack, ProfiledPack
from bizora.providers.copilot import CopilotToolSpec

if TYPE_CHECKING:
    from bizora.copilot.tools import CopilotContext


def pack_tool_specs(pack: DomainPack) -> tuple[CopilotToolSpec, ...]:
    """Convert one pack's declared tools to provider specs."""
    return tuple(
        CopilotToolSpec(
            name=tool.tool_name,
            description=tool.description,
            parameters=dict(tool.input_schema),
        )
        for tool in pack.copilot_tools
    )


def _pack_catalog(pack: DomainPack) -> tuple[ComponentDetail, ...] | None:
    """Return the pack's searchable entries, or None without a profile."""
    if not isinstance(pack, ProfiledPack):
        return None
    return pack.catalog_entries


def _ranked_matches(
    entries: tuple[ComponentDetail, ...], query: str
) -> list[ComponentDetail]:
    """Rank pack entries: exact part number, then label token overlap."""
    wanted = query.strip().lower()
    wanted_tokens = set(tokenize(query))
    scored: list[tuple[tuple[int, int, int, str], ComponentDetail]] = []
    for entry in entries:
        part = (entry.part_number or "").strip().lower()
        exact = 1 if part and part == wanted else 0
        overlap = len(wanted_tokens & set(tokenize(entry.label)))
        if exact == 0 and overlap == 0:
            continue
        scored.append(((exact, overlap, 0 if entry.generic else 1, entry.component_id), entry))
    scored.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2], item[0][3]))
    return [entry for _, entry in scored]


def _search_library(
    pack: DomainPack, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Search one pack's own component library by free text."""
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string."}
    limit = arguments.get("limit", 5)
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        return {"error": "limit must be an integer between 1 and 20."}
    entries = _pack_catalog(pack)
    if entries is None:
        return {"error": f"Pack '{pack.pack_id}' has no searchable component library."}
    matches = _ranked_matches(entries, query.strip())[:limit]
    return {
        "pack_id": pack.pack_id,
        "query": query.strip(),
        "matches": [
            {
                "component_id": entry.component_id,
                "label": entry.label,
                "generic": entry.generic,
                "manufacturer": entry.manufacturer,
                "part_number": entry.part_number,
                "headline": entry.headline,
            }
            for entry in matches
        ],
    }


def _preflight(pack: DomainPack, context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate a pack-library replacement through the pack's own rules."""
    node_id = arguments.get("node_id")
    component_id = arguments.get("component_id")
    if not isinstance(node_id, str) or not node_id.strip():
        return {"error": "node_id must be a non-empty string."}
    if not isinstance(component_id, str) or not component_id.strip():
        return {"error": "component_id must be a non-empty catalog id."}
    entries = _pack_catalog(pack)
    if entries is None:
        return {"error": f"Pack '{pack.pack_id}' has no searchable component library."}
    node = next((n for n in context.graph.nodes if n.id == node_id.strip()), None)
    if node is None:
        return {"error": f"No node has id {node_id.strip()!r} in this revision."}
    detail = next(
        (entry for entry in entries if entry.component_id == component_id.strip()), None
    )
    if detail is None:
        return {
            "error": (
                f"No entry has id {component_id.strip()!r} in the "
                f"'{pack.pack_id}' library."
            )
        }
    try:
        replacement = build_replacement_node(node, detail)
    except BizoraError as exc:
        return {"error": str(exc)}
    patch = GraphPatch(
        patch_id=f"copilot-{pack.pack_id}-preflight",
        base_graph_id=context.graph.graph_id,
        base_version=context.graph.version,
        operation=PatchOperation.REPLACE_NODE,
        target_id=node.id,
        payload={"node": replacement.model_dump(mode="json")},
        rationale=f"Pack preflight check for {detail.label} on {node.id}.",
        requested_by="copilot-pack-preflight",
    )
    findings = pack.check_patch(context.graph, patch)
    return {
        "pack_id": pack.pack_id,
        "compatible": all(
            finding.severity is not PackPreflightSeverity.BLOCK for finding in findings
        ),
        "node_id": node.id,
        "component_id": detail.component_id,
        "candidate_label": detail.label,
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity.value,
                "message": finding.message,
            }
            for finding in findings
        ],
    }


def execute_pack_tool(
    pack: DomainPack,
    context: CopilotContext,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    """Execute one pack tool, or return None when the pack never declared it."""
    if name not in {tool.tool_name for tool in pack.copilot_tools}:
        return None
    try:
        if name.endswith("_search_library"):
            return _search_library(pack, arguments)
        if name.endswith("_preflight"):
            return _preflight(pack, context, arguments)
    except BizoraError as exc:
        return {"error": str(exc)}
    return {"error": f"Pack '{pack.pack_id}' tool {name!r} has no executor."}
