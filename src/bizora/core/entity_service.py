"""Domain detection and entity resolution over methodology graphs."""

from bizora.assets.procedural import build_assembly, build_mesh
from bizora.assets.resolver import package_spec
from bizora.contracts.assets import NodeRenderSpec, ProceduralMesh
from bizora.contracts.components import ComponentDetail
from bizora.contracts.domain import (
    GENERIC_DOMAIN,
    DomainClassification,
    EntityResolution,
    GraphEntities,
    ReplacementCompatibility,
)
from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.contracts.packs import PartRef, ResolutionLevel, SimulationPreview
from bizora.core.entity_registry import (
    DomainProfile,
    check_compatible,
    detect_domain,
    resolve_generic,
    resolve_node,
)
from bizora.packs import DomainPack, ProceduralMeshPack, ProfiledPack, default_registry


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


def pack_for_graph(graph: MethodologyGraph) -> DomainPack | None:
    """Return the routed pack for one graph revision, or None when generic."""
    classification = classify_graph(graph)
    return default_registry().get(classification.domain)


def preview_graph(graph: MethodologyGraph) -> SimulationPreview | None:
    """Return the routed pack's simulation preview, or None when absent."""
    pack = pack_for_graph(graph)
    if pack is None:
        return None
    return pack.simulation_preview(graph)


def classify_graph(graph: MethodologyGraph) -> DomainClassification:
    """Detect the research domain behind one graph revision."""
    nodes = tuple((node.label, node.description, node.kind, node.config) for node in graph.nodes)
    return detect_domain(
        graph.title, _brief_text(graph), nodes, default_registry(), domain_hint=graph.domain_hint
    )


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


_PART_KEYS = ("part", "part_number", "model")
_PACKAGE_KEYS = ("package", "footprint")
# Structural compiler binding a pack may claim (the deep-learning pack
# reads "layer" to resolve compiler-bound nodes with opaque labels).
_LAYER_KEYS = ("layer",)


def _config_text(config: dict[str, object], keys: tuple[str, ...]) -> str | None:
    """Return the first non-blank string value for the given config keys."""
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _entry_package(entry: ComponentDetail) -> str | None:
    """Return the catalog entry's package id, if it states one."""
    for key in _PACKAGE_KEYS:
        configured = entry.default_config.get(key)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    for spec in entry.specs:
        if spec.name.strip().lower() == "package" and spec.value.strip():
            return spec.value.strip()
    return None


def _procedural_mesh(package: str | None) -> ProceduralMesh | None:
    """Return generated geometry for one package id, or None if unknown."""
    if not package:
        return None
    spec = package_spec(package)
    if spec is None:
        return None
    return build_mesh(spec)


def render_specs_for_graph(graph: MethodologyGraph) -> tuple[NodeRenderSpec, ...]:
    """Resolve every node to a 3D visual; nodes without one are skipped.

    Part identity flows node config -> part ladder -> catalog package ->
    generated mesh, so a replaced node renders the package of its actual
    part. Registry hits with model URIs ride along as measured visuals.
    Pack assemblies come first: a pack that knows the exact part
    renders its own solids, and the generic package path only covers
    parts no pack models.
    """
    pack = pack_for_graph(graph)
    if pack is None:
        return ()
    catalog: dict[str, ComponentDetail] = {}
    if isinstance(pack, ProfiledPack):
        catalog = {entry.component_id: entry for entry in pack.catalog_entries}
    specs: list[NodeRenderSpec] = []
    for node in graph.nodes:
        config = node.config if isinstance(node.config, dict) else {}
        raw_text = f"{node.label} {node.description or ''}".strip() or node.label
        bound_layer = _config_text(config, _LAYER_KEYS)
        resolution = pack.resolve_part(
            PartRef(
                raw_text=raw_text,
                part_number=_config_text(config, _PART_KEYS),
                package=_config_text(config, _PACKAGE_KEYS),
                parameters={"layer": bound_layer} if bound_layer is not None else {},
            )
        )
        if resolution.level is ResolutionLevel.UNRESOLVED:
            continue
        render = pack.render_spec(resolution)
        mesh = None
        if isinstance(pack, ProceduralMeshPack):
            assembly = pack.procedural_spec(config, resolution)
            if assembly:
                mesh = build_assembly(assembly)
        if mesh is None:
            package = _config_text(config, _PACKAGE_KEYS)
            if package is None and resolution.asset_key is not None:
                entry = catalog.get(resolution.asset_key)
                if entry is not None:
                    package = _entry_package(entry)
            mesh = _procedural_mesh(package)
        if not render.asset_uri and mesh is None:
            continue
        specs.append(
            NodeRenderSpec(
                node_id=node.id,
                label=render.label,
                asset_uri=render.asset_uri,
                fallback_package=render.fallback_package,
                illustrative=render.illustrative,
                mesh=mesh,
            )
        )
    return tuple(specs)


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
