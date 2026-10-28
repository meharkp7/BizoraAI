"""Deterministic research copilot over the catalog and graph state.

The copilot is conversational but never generative: every answer is computed
from the component registry, the entity resolutions, and the stored graph
revision. It finds and compares components, explains compatibility, and
proposes configuration changes as structured proposals that the user must
explicitly approve; it never writes anything itself.
"""

from __future__ import annotations

import re
from typing import Any

from bizora.contracts.components import (
    ComponentDetail,
    CopilotCard,
    CopilotProposal,
    CopilotResponse,
)
from bizora.contracts.domain import EntityResolution, GraphEntities
from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.core.component_catalog import (
    CATALOG,
    get_component,
    search_components,
)
from bizora.core.component_service import build_replacement_node, preflight_replacement
from bizora.core.entity_service import resolve_graph
from bizora.core.errors import BizoraError

COMPARE_SPLIT = re.compile(
    r"\s+(?:vs\.?|versus|against|and|or|with|compared?\s+to)\s+", re.IGNORECASE
)
SET_PATTERN = re.compile(
    r"set\s+(?P<key>[a-zA-Z0-9_]+)\s+to\s+(?P<value>[^,;]+?)(?:\s+on\s+(?P<node>[a-zA-Z0-9_.:-]+))?\s*$",
    re.IGNORECASE,
)
REPLACE_PATTERN = re.compile(
    r"replace\s+(?P<target>.+?)\s+with\s+(?P<candidate>.+?)\s*$",
    re.IGNORECASE,
)
EXPLAIN_PATTERN = re.compile(
    r"(?:explain|why)(?:\s+is)?\s+(?P<subject>.+?)(?:\s+(?:compatible|incompatible))?\s*$",
    re.IGNORECASE,
)
FIND_PATTERN = re.compile(
    r"(?:find|search|show|list|looking\s+for|suggest|recommend)\s+(?P<terms>.+?)\s*$",
    re.IGNORECASE,
)

HELP_TEXT = (
    "I can search the component library, compare entries, validate a replacement "
    "against the selected graph node, and propose configuration changes. "
    "Try 'find NPN transistor', 'compare NF4 vs FP16', "
    "'replace the access transistors with 2N3904', or 'set sampling_rate_hz to 16000'. "
    "I never apply changes myself: every proposal waits for your approval."
)


def _resolve_component_reference(text: str) -> ComponentDetail | None:
    """Match a component by id, part number, or unique label substring."""
    cleaned = text.strip().lower().strip("\"'")
    if not cleaned:
        return None
    if cleaned in CATALOG:
        return CATALOG[cleaned]
    for detail in CATALOG.values():
        if detail.part_number and detail.part_number.lower() == cleaned:
            return detail
    matches = [detail for detail in CATALOG.values() if cleaned in detail.label.lower()]
    if len(matches) == 1:
        return matches[0]
    for detail in matches:
        if detail.label.lower() == cleaned:
            return detail
    return matches[0] if matches else None


def _resolve_node_reference(
    graph: MethodologyGraph, text: str, selected_node_id: str | None
) -> GraphNode | None:
    """Match a node by selection, id, or unique label substring."""
    cleaned = text.strip().lower().strip("\"'")
    if cleaned in ("", "this", "this node", "this component", "it", "selected", "selected node"):
        if selected_node_id:
            return next((n for n in graph.nodes if n.id == selected_node_id), None)
        return None
    for node in graph.nodes:
        if node.id.lower() == cleaned:
            return node
    matches = [node for node in graph.nodes if cleaned in node.label.lower()]
    if len(matches) == 1:
        return matches[0]
    for node in matches:
        if node.label.lower() == cleaned:
            return node
    return None


def _entity_for(entities: GraphEntities, node_id: str) -> EntityResolution | None:
    return next((e for e in entities.entities if e.node_id == node_id), None)


def _component_card(detail: ComponentDetail) -> CopilotCard:
    identity = (
        f"Exact part {detail.part_number} ({detail.manufacturer})"
        if not detail.generic
        else "Correctly identified generic (no exact part)"
    )
    lines = [identity, detail.headline]
    if detail.specs:
        lines.append(
            "Specs: " + "; ".join(f"{spec.name} {spec.value}" for spec in detail.specs[:4])
        )
    if detail.datasheet_url or detail.reference_url:
        lines.append(f"Reference: {detail.datasheet_url or detail.reference_url}")
    else:
        lines.append("Reference: not verified yet")
    return CopilotCard(
        kind="component",
        title=detail.label,
        body="\n".join(lines),
        component_ids=(detail.component_id,),
    )


def _preflight_summary(
    graph: MethodologyGraph, node: GraphNode, detail: ComponentDetail
) -> tuple[str, CopilotProposal | None]:
    """Summarize compatibility and build an approvable proposal on success."""
    try:
        preflight = preflight_replacement(graph, node.id, detail.component_id)
    except BizoraError as exc:
        return f"I could not validate that swap: {exc}", None
    kept = len(preflight.preserved_edge_ids)
    if preflight.compatible:
        proposal = CopilotProposal(
            node_id=node.id,
            component_id=detail.component_id,
            kind=detail.kind,
            label=detail.label,
            description=detail.description,
            config=dict(
                build_replacement_node(node, detail).config,
            ),
            rationale=f"Copilot proposal: replace {node.id} with {detail.label}.",
        )
        notes = "; ".join(w.message for w in preflight.warnings) or "no warnings"
        return (
            f"{detail.label} is compatible with {node.label}: all known interfaces "
            f"are preserved, {kept} connection(s) survive, and {notes}. "
            "Review the proposal card and approve to create a new revision.",
            proposal,
        )
    missing = "; ".join(m.reason for m in preflight.missing_interfaces)
    return (
        f"{detail.label} is not compatible with {node.label}: {missing} "
        f"Pick a component that keeps those interfaces, or rewire first.",
        None,
    )


def _compare_cards(first: ComponentDetail, second: ComponentDetail) -> CopilotCard:
    rows = ["| Spec | " + first.label + " | " + second.label + " |"]
    names = [s.name for s in first.specs[:6]]
    for name in names:
        left = next((s.value for s in first.specs if s.name == name), "-")
        right = next((s.value for s in second.specs if s.name == name), "-")
        rows.append(f"| {name} | {left} | {right} |")
    for spec in second.specs[:6]:
        if spec.name not in names:
            rows.append(f"| {spec.name} | - | {spec.value} |")
    left_if = ", ".join(sorted({i.kind for i in first.interfaces})) or "none declared"
    right_if = ", ".join(sorted({i.kind for i in second.interfaces})) or "none declared"
    rows.append(f"| Interfaces | {left_if} | {right_if} |")
    rows.append(
        f"| Identity | {'generic' if first.generic else first.part_number} "
        f"| {'generic' if second.generic else second.part_number} |"
    )
    return CopilotCard(
        kind="comparison",
        title=f"{first.label} vs {second.label}",
        body="\n".join(rows),
        component_ids=(first.component_id, second.component_id),
    )


def _parse_value(raw: str) -> Any:
    text = raw.strip().strip("\"'")
    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def answer_copilot(
    graph: MethodologyGraph, message: str, selected_node_id: str | None = None
) -> CopilotResponse:
    """Answer one copilot message against the catalog and graph state."""
    entities = resolve_graph(graph)
    text = message.strip()
    lowered = text.lower()

    if lowered in ("help", "what can you do?", "what can you do", "?"):
        return CopilotResponse(reply=HELP_TEXT, cards=())

    if any(word in lowered for word in ("status", "summary", "overview", "what is this")):
        classification = entities.classification
        generic = sum(1 for e in entities.entities if e.generic)
        exact = len(entities.entities) - generic
        return CopilotResponse(
            reply=(
                f"This revision is classified as {classification.domain} "
                f"({round(classification.confidence * 100)}% confidence) with {exact} "
                f"exact and {generic} generic node(s). Select a node and ask me to "
                "find a replacement, or ask for help."
            ),
            cards=(),
        )

    if any(word in lowered for word in ("run", "execute", "simulate", "simulation")):
        return CopilotResponse(
            reply=(
                "The only connected execution adapter is bizora.deterministic-test, "
                "which validates the revision and persists a real run record "
                "(status, seed, graph version). Domain simulators (SPICE-class circuit "
                "simulation, hardware-in-the-loop, LLM inference) are not connected, "
                "so I cannot execute those here. Use Run revision for a genuine "
                "validation run, and treat anything else as unsupported."
            ),
            cards=(),
        )

    set_match = SET_PATTERN.search(text)
    if set_match:
        key = set_match.group("key")
        value = _parse_value(set_match.group("value"))
        node_ref = set_match.group("node") or "this"
        node = _resolve_node_reference(graph, node_ref, selected_node_id)
        if node is None:
            return CopilotResponse(
                reply=(
                    "Select the node to configure first, or name it, for example "
                    "'set sampling_rate_hz to 16000 on sampler'."
                ),
                cards=(),
            )
        config_proposal = CopilotProposal(
            node_id=node.id,
            component_id=None,
            kind=node.kind.value,
            label=node.label,
            description=node.description,
            config={**node.config, key: value},
            rationale=f"Copilot proposal: set {key} to {value!r} on {node.id}.",
        )
        return CopilotResponse(
            reply=(
                f"Ready to set {key} to {value!r} on {node.label}. Approve the "
                "proposal card to write it as a new revision."
            ),
            cards=(
                CopilotCard(
                    kind="proposal",
                    title=f"Set {key} on {node.label}",
                    body=f"{key} = {value!r} (was {node.config.get(key, 'unset')!r})",
                    component_ids=(),
                    node_id=node.id,
                ),
            ),
            proposal=config_proposal,
        )

    replace_match = REPLACE_PATTERN.search(text)
    if replace_match:
        node = _resolve_node_reference(graph, replace_match.group("target"), selected_node_id)
        detail = _resolve_component_reference(replace_match.group("candidate"))
        if node is None:
            return CopilotResponse(
                reply=(
                    "I could not identify which node to replace. Select it in the "
                    "graph, or name it exactly."
                ),
                cards=(),
            )
        if detail is None:
            return CopilotResponse(
                reply=(
                    "I could not find that component in the library. Ask me to "
                    "'find' it first and I will show the closest matches."
                ),
                cards=(),
            )
        summary, proposal = _preflight_summary(graph, node, detail)
        proposal_cards: list[CopilotCard] = [_component_card(detail)]
        if proposal is not None:
            proposal_cards.append(
                CopilotCard(
                    kind="proposal",
                    title=f"Replace {node.label} with {detail.label}",
                    body=summary,
                    component_ids=(detail.component_id,),
                    node_id=node.id,
                )
            )
        return CopilotResponse(reply=summary, cards=tuple(proposal_cards), proposal=proposal)

    if "compare" in lowered or COMPARE_SPLIT.search(text):
        parts = COMPARE_SPLIT.split(text)
        candidates = [p for p in parts if p.strip().lower() not in ("compare",)]
        if len(candidates) >= 2:
            first = _resolve_component_reference(candidates[0].replace("compare", "", 1))
            second = _resolve_component_reference(candidates[1])
            if first is not None and second is not None:
                card = _compare_cards(first, second)
                return CopilotResponse(
                    reply=(
                        f"Compared {first.label} with {second.label}. Spec values "
                        "are nominal catalog values; confirm limits in the linked "
                        "reference before building."
                    ),
                    cards=(card,),
                )
        return CopilotResponse(
            reply="Name two library components, for example 'compare NF4 vs FP16'.",
            cards=(),
        )

    explain_match = EXPLAIN_PATTERN.search(text)
    if explain_match or "compatible" in lowered:
        subject = explain_match.group("subject") if explain_match else text
        detail = _resolve_component_reference(subject)
        node = _resolve_node_reference(graph, subject, selected_node_id)
        if detail is not None and node is not None and detail.component_id:
            summary, _ = _preflight_summary(graph, node, detail)
            return CopilotResponse(reply=summary, cards=(_component_card(detail),))
        if detail is not None:
            evidence = "; ".join(e.source for e in detail.evidence) or "catalog entry"
            return CopilotResponse(
                reply=(f"{detail.label}: {detail.description} Grounded by {evidence}."),
                cards=(_component_card(detail),),
            )
        if node is not None:
            entity = _entity_for(entities, node.id)
            if entity is None:
                return CopilotResponse(reply="That node has no entity resolution.", cards=())
            if entity.generic:
                return CopilotResponse(
                    reply=(
                        f"{node.label} is a generic placeholder: the graph does not "
                        "name an exact entity here. Ask me to find a replacement to "
                        "pin it to an exact part."
                    ),
                    cards=(),
                )
            interfaces = ", ".join(i.kind for i in entity.interfaces) or "none"
            return CopilotResponse(
                reply=(
                    f"{node.label} resolves to {entity.display_label} "
                    f"({entity.entity_type}) with interfaces {interfaces}, grounded "
                    f"by {', '.join(entity.matched_terms) or 'registry defaults'}."
                ),
                cards=(),
            )
        return CopilotResponse(
            reply="Name a library component or a graph node to explain.", cards=()
        )

    find_match = FIND_PATTERN.search(text)
    if find_match:
        terms = find_match.group("terms")
        results = search_components(terms, limit=5)
        if not results:
            return CopilotResponse(
                reply=f"The library has no matches for {terms!r}. Try fewer words.",
                cards=(),
            )
        found_cards: list[CopilotCard] = []
        for hit in results:
            found = get_component(hit.component_id)
            if found is not None:
                found_cards.append(_component_card(found))
        names = ", ".join(hit.label for hit in results)
        return CopilotResponse(
            reply=f"Closest library matches: {names}.",
            cards=tuple(found_cards),
        )

    # Fallback: best-effort search over the raw message terms.
    results = search_components(text, limit=5)
    if results:
        fallback_cards: list[CopilotCard] = []
        for hit in results:
            found = get_component(hit.component_id)
            if found is not None:
                fallback_cards.append(_component_card(found))
        return CopilotResponse(
            reply=(
                f"I interpreted that as a library search: {', '.join(r.label for r in results)}. "
                "Ask for 'help' to see everything I can do."
            ),
            cards=tuple(fallback_cards),
        )
    return CopilotResponse(reply=HELP_TEXT, cards=())
