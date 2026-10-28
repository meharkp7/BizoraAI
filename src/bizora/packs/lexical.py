"""Data-driven domain pack harness.

LexicalPack implements the DomainPack protocol from pack-owned data:
detection signals, entity types, and catalog entries. Every behavior here
is generic text matching and interface comparison; all vocabulary lives in
the pack data modules, never in this logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from bizora.contracts.components import ComponentDetail
from bizora.contracts.graph import GraphNode, MethodologyGraph
from bizora.contracts.packs import (
    CopilotToolSpec,
    DomainTag,
    PackComponentKind,
    PackPreflightFinding,
    PackPreflightSeverity,
    PackVocabulary,
    PartRef,
    PartResolution,
    RenderSpec,
    ResolutionConfidence,
    ResolutionLevel,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.entity_registry import (
    DomainProfile,
    EntityTypeDef,
    InterfaceDef,
    check_compatible,
    match_terms,
    resolve_node,
    tokenize,
)


def power_iface(voltage_key: str | None = None) -> InterfaceDef:
    """Build a power interface, optionally pinned to a config voltage key."""
    params = {"voltage": voltage_key} if voltage_key else {}
    return InterfaceDef(name="power", kind="power", params=params)


def data_iface() -> InterfaceDef:
    """Build a plain data interface."""
    return InterfaceDef(name="data", kind="data")


def tensor_iface() -> InterfaceDef:
    """Build a tensor interface for array-shaped dataflow."""
    return InterfaceDef(name="tensor", kind="tensor")


def _tool_slug(pack_id: str) -> str:
    return pack_id.replace("-", "_").replace(".", "_")


class LexicalPack:
    """A DomainPack driven entirely by caller-supplied data tables."""

    def __init__(
        self,
        *,
        pack_id: str,
        pack_version: str,
        display: str,
        signals: tuple[str, ...],
        threshold: int,
        entity_types: tuple[EntityTypeDef, ...],
        catalog: Sequence[dict[str, Any]],
        simulator_adapter_ids: tuple[str, ...] = (),
    ) -> None:
        self._pack_id = pack_id
        self._pack_version = pack_version
        self._display = display
        self._signals = signals
        self._threshold = threshold
        self._profile = DomainProfile(
            domain=pack_id,
            display=display,
            signals=signals,
            entity_types=entity_types,
            threshold=threshold,
        )
        self._catalog = tuple(ComponentDetail.model_validate(entry) for entry in catalog)
        self._simulators = simulator_adapter_ids
        self._vocabulary = PackVocabulary(
            kinds=tuple(
                PackComponentKind(kind_id=item.type_id, display_label=item.display)
                for item in entity_types
            )
        )
        self._kind_labels = {item.type_id: item.display for item in entity_types}
        slug = _tool_slug(pack_id)
        self._tools = (
            CopilotToolSpec(
                tool_name=f"{slug}_search_library",
                description=f"Search the {display} component library by free text.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            CopilotToolSpec(
                tool_name=f"{slug}_preflight",
                description=f"Validate a {display} replacement against one graph node.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "component_id": {"type": "string"},
                    },
                    "required": ["node_id", "component_id"],
                },
            ),
        )

    @property
    def pack_id(self) -> str:
        """Return the stable pack identifier."""
        return self._pack_id

    @property
    def pack_version(self) -> str:
        """Return the exact pack version."""
        return self._pack_version

    @property
    def vocabulary(self) -> PackVocabulary:
        """Return the component vocabulary derived from pack entity types."""
        return self._vocabulary

    @property
    def simulator_adapter_ids(self) -> tuple[str, ...]:
        """Return adapter ids this pack can run."""
        return self._simulators

    @property
    def copilot_tools(self) -> tuple[CopilotToolSpec, ...]:
        """Return the pack-provided tools the copilot may call."""
        return self._tools

    @property
    def profile(self) -> DomainProfile:
        """Return the detection signals and entity types this pack handles."""
        return self._profile

    @property
    def catalog_entries(self) -> tuple[ComponentDetail, ...]:
        """Return the validated catalog entries this pack contributes."""
        return self._catalog

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        """Score pack affinity: matched signals over the open-vocabulary tags."""
        matched = match_terms("\n".join(tag.label for tag in tags), self._signals)
        if len(matched) < self._threshold:
            return 0.0
        return round(len(matched) / (len(matched) + 2), 3)

    def resolve_part(self, ref: PartRef) -> PartResolution:
        """Resolve one part mention down the exact/family/category ladder."""
        exact = self._match_exact(ref.part_number)
        if exact is not None:
            return PartResolution(
                level=ResolutionLevel.EXACT,
                confidence=ResolutionConfidence.FROM_PAPER,
                pack_id=self._pack_id,
                kind_id=exact.entity_type,
                asset_key=exact.component_id,
                reason=f"Exact part-number match on {exact.part_number} ({exact.label}).",
            )
        family = self._match_family(ref.package)
        if family is not None:
            return PartResolution(
                level=ResolutionLevel.FAMILY,
                confidence=ResolutionConfidence.MATCHED,
                pack_id=self._pack_id,
                kind_id=family.entity_type,
                asset_key=family.component_id,
                reason=(
                    f"Package {ref.package} matches {family.label}; "
                    "exact part number not stated."
                ),
            )
        category, tokens = self._match_category(ref.raw_text)
        if category is not None:
            return PartResolution(
                level=ResolutionLevel.CATEGORY,
                confidence=ResolutionConfidence.MATCHED,
                pack_id=self._pack_id,
                kind_id=category.entity_type,
                asset_key=category.component_id,
                reason=(
                    f"Label overlap on {', '.join(tokens)} suggests {category.label}; "
                    "treat as representative, not exact."
                ),
            )
        return PartResolution(
            level=ResolutionLevel.UNRESOLVED,
            confidence=ResolutionConfidence.ASSUMED,
            pack_id=self._pack_id,
            reason=f"No {self._display} catalog entry matches {ref.raw_text!r}.",
        )

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        """Return the 3D render spec for one resolved part.

        No asset registry exists yet (Phase 4), so every visual stays
        illustrative; the asset key pins which entry it represents.
        """
        if resolution.level is ResolutionLevel.UNRESOLVED or resolution.kind_id is None:
            return RenderSpec(label="Unresolved part", illustrative=True)
        label = self._kind_labels.get(resolution.kind_id, resolution.kind_id)
        return RenderSpec(
            label=label,
            asset_uri=None,
            fallback_package=resolution.asset_key or resolution.kind_id,
            illustrative=True,
        )

    def check_patch(
        self, graph: MethodologyGraph, patch: GraphPatch
    ) -> tuple[PackPreflightFinding, ...]:
        """Block replacements that drop interfaces the pack profile knows."""
        if patch.operation is not PatchOperation.REPLACE_NODE:
            return ()
        target = next((node for node in graph.nodes if node.id == patch.target_id), None)
        payload_node = patch.payload.get("node")
        if target is None or not isinstance(payload_node, dict):
            return ()
        try:
            candidate = GraphNode.model_validate(payload_node)
        except ValidationError:
            return ()
        old = resolve_node(
            self._profile,
            target.id,
            target.label,
            target.description,
            target.kind.value,
            target.config,
        )
        new = resolve_node(
            self._profile,
            candidate.id,
            candidate.label,
            candidate.description,
            candidate.kind.value,
            candidate.config,
        )
        compatibility = check_compatible(old, new, ())
        rule_id = f"{_tool_slug(self._pack_id)}_interface_preserved"
        return tuple(
            PackPreflightFinding(
                rule_id=rule_id,
                severity=PackPreflightSeverity.BLOCK,
                message=missing.reason,
            )
            for missing in compatibility.missing_interfaces
        )

    def _match_exact(self, part_number: str | None) -> ComponentDetail | None:
        if not part_number:
            return None
        wanted = part_number.strip().lower()
        for entry in self._catalog:
            if entry.part_number and entry.part_number.lower() == wanted:
                return entry
        return None

    def _match_family(self, package: str | None) -> ComponentDetail | None:
        if not package:
            return None
        wanted = package.strip().lower()
        for entry in self._catalog:
            configured = entry.default_config.get("package")
            if isinstance(configured, str) and configured.strip().lower() == wanted:
                return entry
            for spec in entry.specs:
                if spec.name.lower() == "package" and spec.value.strip().lower() == wanted:
                    return entry
        return None

    def _match_category(self, raw_text: str) -> tuple[ComponentDetail | None, tuple[str, ...]]:
        wanted = set(tokenize(raw_text))
        if not wanted:
            return None, ()
        best: ComponentDetail | None = None
        best_key = (0, 0, 0)
        for index, entry in enumerate(self._catalog):
            overlap = len(wanted & set(tokenize(entry.label)))
            key = (overlap, 1 if entry.generic else 0, -index)
            if overlap > 0 and key > best_key:
                best = entry
                best_key = key
        if best is None:
            return None, ()
        matched = tuple(sorted(wanted & set(tokenize(best.label))))
        return best, matched
