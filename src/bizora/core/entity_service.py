"""Domain detection and entity resolution over methodology graphs."""

from bizora.contracts.domain import (
    GENERIC_DOMAIN,
    DomainClassification,
    EntityResolution,
    GraphEntities,
    ReplacementCompatibility,
)
from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.core.entity_registry import (
    DomainProfile,
    check_compatible,
    detect_domain,
    resolve_generic,
    resolve_node,
)
from bizora.packs import ProfiledPack, default_registry


def profile_for_domain(pack_id: str) -> DomainProfile | None:
    """Return the detection profile for one routed pack id, or None."""
    pack = default_registry().get(pack_id)
    if pack is not None and isinstance(pack, ProfiledPack):
        return pack.profile
    return None


def _brief_text(graph: MethodologyGraph) -> str:
    brief = graph.brief
    if brief is None:
        return ""
    parts = [brief.problem or ""]
    parts.extend(brief.objectives)
    parts.extend(brief.findings)
    parts.extend(brief.limitations)
    return " ".join(parts)


def classify_graph(graph: MethodologyGraph) -> DomainClassification:
    """Detect the research domain behind one graph revision."""
    nodes = tuple((node.label, node.description, node.kind, node.config) for node in graph.nodes)
    return detect_domain(graph.title, _brief_text(graph), nodes, default_registry())


def resolve_graph(graph: MethodologyGraph) -> GraphEntities:
    """Resolve every node of one graph revision to registry entities."""
    classification = classify_graph(graph)
    profile = profile_for_domain(classification.domain)
    entities: list[EntityResolution] = []
    for node in graph.nodes:
        if profile is None or classification.domain == GENERIC_DOMAIN:
            entities.append(resolve_generic(node.id, node.label))
        else:
            entities.append(
                resolve_node(profile, node.id, node.label, node.description, node.kind, node.config)
            )
    return GraphEntities(
        project_id=graph.project_id,
        graph_id=graph.graph_id,
        version=graph.version,
        classification=classification,
        entities=tuple(entities),
    )


def check_replacement(
    graph: MethodologyGraph, target_id: str, replacement: GraphNode
) -> ReplacementCompatibility:
    """Check a replacement node against its predecessor's interfaces."""
    classification = classify_graph(graph)
    profile = profile_for_domain(classification.domain)
    existing = next(node for node in graph.nodes if node.id == target_id)
    if profile is None or classification.domain == GENERIC_DOMAIN:
        old = resolve_generic(existing.id, existing.label)
        new = resolve_generic(replacement.id, replacement.label)
    else:
        old = resolve_node(
            profile,
            existing.id,
            existing.label,
            existing.description,
            existing.kind,
            existing.config,
        )
        new = resolve_node(
            profile,
            replacement.id,
            replacement.label,
            replacement.description,
            replacement.kind,
            replacement.config,
        )
    incident = tuple(
        edge.id for edge in graph.edges if edge.source == target_id or edge.target == target_id
    )
    return check_compatible(old, new, incident)
