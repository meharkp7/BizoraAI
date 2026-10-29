"""Replacement preflight: validate a catalog component against a graph node.

The preflight answers three questions before any revision is created:
which interfaces would break, which connections survive, and which
configuration the replacement needs. Blocking failures reuse the same
registry compatibility check that guards REPLACE_NODE patches, so the
preview and the patch can never disagree; declared catalog interfaces are
compared directly as well, since a replacement label may not re-resolve
through registry vocabulary.
"""

from __future__ import annotations

from typing import Any

from bizora.contracts.components import (
    CompatibilityPreflight,
    ComponentDetail,
    ConstraintWarning,
)
from bizora.contracts.domain import (
    GENERIC_DOMAIN,
    EntityResolution,
    InterfaceSpec,
    MissingInterface,
)
from bizora.contracts.graph import GraphNode, MethodologyGraph, NodeKind
from bizora.core.component_catalog import get_component
from bizora.core.entity_registry import resolve_generic, resolve_node
from bizora.core.entity_service import (
    check_replacement,
    classify_graph,
    profile_for_domain,
    resolve_graph,
)
from bizora.core.errors import BizoraError, ErrorCode


def _validate_config(component: ComponentDetail, config: dict[str, Any]) -> dict[str, Any]:
    """Merge overrides over component defaults and check them against the schema."""
    merged: dict[str, Any] = {**component.default_config, **config}
    schema = {field.key: field for field in component.config_schema}
    errors: list[str] = []
    for key, field in schema.items():
        value = merged.get(key, field.default)
        if field.required and (key not in merged or merged[key] in (None, "")):
            errors.append(f"Configuration key {key!r} is required.")
            continue
        if field.type == "enum" and value is not None and str(value) not in field.options:
            errors.append(f"Configuration key {key!r} must be one of {', '.join(field.options)}.")
        elif field.type == "number" and value is not None and not isinstance(value, (int, float)):
            errors.append(f"Configuration key {key!r} must be a number.")
        elif field.type == "boolean" and value is not None and not isinstance(value, bool):
            errors.append(f"Configuration key {key!r} must be true or false.")
    if errors:
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            "The replacement configuration is invalid.",
            details={"component_id": component.component_id, "errors": errors},
        )
    return merged


def build_replacement_node(
    target: GraphNode,
    component: ComponentDetail,
    config: dict[str, Any] | None = None,
) -> GraphNode:
    """Build the in-place replacement node for a catalog component.

    The node keeps the target ID (so connections survive) and the target
    evidence, provenance, and shapes; identity and configuration come from
    the catalog entry.
    """
    merged = _validate_config(component, config or {})
    return GraphNode(
        id=target.id,
        kind=NodeKind(component.kind),
        label=component.label,
        description=component.description,
        config=merged,
        input_shape=target.input_shape,
        output_shape=target.output_shape,
        evidence=target.evidence,
        provenance=target.provenance,
        confidence=target.confidence,
    )


def _resolve_candidate(
    graph: MethodologyGraph, candidate: GraphNode, component: ComponentDetail
) -> EntityResolution:
    """Resolve the candidate node through the graph's domain profile."""
    classification = classify_graph(graph)
    profile = profile_for_domain(classification.domain)
    if profile is None or classification.domain == GENERIC_DOMAIN:
        return resolve_generic(candidate.id, candidate.label)
    resolved = resolve_node(
        profile,
        candidate.id,
        candidate.label,
        candidate.description,
        candidate.kind.value,
        candidate.config,
    )
    if resolved.generic:
        # The catalog pins the identity even when registry vocabulary cannot
        # re-derive it from the generated label. Catalog parts are physical
        # by definition; the render declaration comes from the entry's
        # entity type, falling back to a generic symbol when unknown.
        render = next(
            (
                entity
                for entity in profile.entity_types
                if entity.type_id == component.entity_type
            ),
            None,
        )
        return EntityResolution(
            node_id=candidate.id,
            domain=classification.domain,
            entity_type=component.entity_type,
            display_label=component.label,
            generic=component.generic,
            category=component.category,
            physical=True,
            symbol=render.symbol if render is not None else "generic",
            model_3d=render.model_3d if render is not None else None,
            interfaces=tuple(
                InterfaceSpec(name=iface.name, kind=iface.kind, params=dict(iface.params))
                for iface in component.interfaces
            ),
            matched_terms=(),
            confidence=0.5,
        )
    return resolved


def _direct_missing(old: EntityResolution, component: ComponentDetail) -> list[MissingInterface]:
    """Compare declared catalog interfaces against the predecessor's."""
    if old.generic or not old.interfaces:
        return []
    new_kinds = {iface.kind for iface in component.interfaces}
    return [
        MissingInterface(
            kind=iface.kind,
            reason=(
                f"Catalog entry {component.component_id!r} exposes no {iface.kind!r} interface."
            ),
        )
        for iface in old.interfaces
        if iface.kind not in new_kinds
    ]


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _constraint_warnings(
    component: ComponentDetail, merged_config: dict[str, Any]
) -> list[ConstraintWarning]:
    """Check configured rails against the component's declared limits."""
    warnings: list[ConstraintWarning] = []
    supply = _as_float(merged_config.get("supply_V", merged_config.get("output_V")))
    if supply is not None:
        low = _as_float(component.constraints.get("supply_min_V"))
        high = _as_float(component.constraints.get("supply_max_V"))
        if low is not None and supply < low:
            warnings.append(
                ConstraintWarning(
                    code="supply_below_minimum",
                    message=(
                        f"Configured {supply} V is below the {component.part_number or component.label} "
                        f"minimum of {low} V."
                    ),
                )
            )
        if high is not None and supply > high:
            warnings.append(
                ConstraintWarning(
                    code="supply_above_maximum",
                    message=(
                        f"Configured {supply} V exceeds the {component.part_number or component.label} "
                        f"maximum of {high} V."
                    ),
                )
            )
    return warnings


def preflight_replacement(
    graph: MethodologyGraph,
    node_id: str,
    component_id: str,
    config: dict[str, Any] | None = None,
) -> CompatibilityPreflight:
    """Validate replacing one node with a catalog component (no writes)."""
    target = next((node for node in graph.nodes if node.id == node_id), None)
    if target is None:
        raise BizoraError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Node {node_id!r} does not exist in this revision.",
            details={"node_id": node_id},
        )
    component = get_component(component_id)
    if component is None:
        raise BizoraError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Component {component_id!r} is not in the catalog.",
            details={"component_id": component_id},
        )
    candidate = build_replacement_node(target, component, config)
    registry_check = check_replacement(graph, node_id, candidate)
    entities = resolve_graph(graph)
    old = next(entity for entity in entities.entities if entity.node_id == node_id)
    missing = list(registry_check.missing_interfaces)
    seen = {item.kind for item in missing}
    for item in _direct_missing(old, component):
        if item.kind not in seen:
            missing.append(item)
            seen.add(item.kind)
    warnings = _constraint_warnings(component, candidate.config)
    classification = entities.classification
    if classification.domain != GENERIC_DOMAIN and component.domain != classification.domain:
        warnings.append(
            ConstraintWarning(
                code="cross_domain",
                message=(
                    f"{component.label} belongs to {component.domain}, but this graph "
                    f"is classified as {classification.domain}. Interfaces are still "
                    "validated; review the pinout before applying."
                ),
            )
        )
    schema_keys = {field.key for field in component.config_schema}
    known_keys = schema_keys | set(component.default_config)
    unknown = sorted(key for key in (config or {}) if key not in known_keys)
    if unknown:
        warnings.append(
            ConstraintWarning(
                code="config_key_unknown",
                message=(
                    "Configuration keys not in the component schema are stored "
                    f"as-is: {', '.join(unknown)}."
                ),
            )
        )
    if old.generic and not component.generic:
        warnings.append(
            ConstraintWarning(
                code="info_identity_upgrade",
                message=(
                    f"This upgrade pins {candidate.id} to exact part "
                    f"{component.part_number or component.label}."
                ),
            )
        )
    return CompatibilityPreflight(
        compatible=not missing,
        target_node_id=node_id,
        component_id=component_id,
        missing_interfaces=tuple(missing),
        preserved_edge_ids=registry_check.incident_edge_ids,
        warnings=tuple(warnings),
        candidate=_resolve_candidate(graph, candidate, component),
        candidate_label=component.label,
    )
