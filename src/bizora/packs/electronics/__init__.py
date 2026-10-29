"""Electronics domain pack: circuits, discretes, ICs, and measurement.

This is the Phase 2 launch pack: the catalog entries and detection
profile moved verbatim from the former core registry into pack data,
wired to the generic pack harness. Phase 5 connected the local ngspice
adapter plus a netlist/BOM/preflight simulation preview.

Phase 4 wires an asset registry for 3D render specs. No measured model
bytes exist yet (fetching real corpora needs license verification, so
no downloads happen here), and the registry therefore starts empty:
every render spec stays illustrative until verified models land.

Per-part assemblies model the flagship parts from outline dimensions
(PDIP, TO-220, VSSOP); parts without a modeled visual keep the
generic package fallback.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from bizora.assets.registry import AssetRegistry
from bizora.contracts.assets import AssetManifest, ProceduralSpec
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.packs import (
    CopilotToolSpec,
    DomainTag,
    PackPreflightFinding,
    PackVocabulary,
    PartRef,
    PartResolution,
    RenderSpec,
    SimulationPreview,
    TelemetryMapping,
)
from bizora.contracts.patches import GraphPatch
from bizora.packs.electronics.data import (
    COMPONENTS,
    DISPLAY,
    ENTITY_TYPES,
    PACK_ID,
    PACK_VERSION,
    PART_VISUALS,
    SIGNALS,
    THRESHOLD,
    VISUAL_SPECS,
)
from bizora.packs.electronics.preview import build_preview
from bizora.packs.lexical import LexicalPack

if TYPE_CHECKING:
    from bizora.contracts.components import ComponentDetail
    from bizora.core.entity_registry import DomainProfile


class ElectronicsPack:
    """Electronics pack behind the DomainPack/ProfiledPack protocols.

    Everything delegates to the generic lexical harness except the
    render path, which serves per-part assemblies with part labels.
    """

    def __init__(self) -> None:
        self._lexical = LexicalPack(
            pack_id=PACK_ID,
            pack_version=PACK_VERSION,
            display=DISPLAY,
            signals=SIGNALS,
            threshold=THRESHOLD,
            entity_types=ENTITY_TYPES,
            catalog=COMPONENTS,
            simulator_adapter_ids=("bizora.ngspice",),
            assets=AssetRegistry(AssetManifest(registry_version="1.0.0")),
            simulation_preview_builder=build_preview,
        )

    @property
    def pack_id(self) -> str:
        """Return the stable pack identifier."""
        return self._lexical.pack_id

    @property
    def pack_version(self) -> str:
        """Return the exact pack version."""
        return self._lexical.pack_version

    @property
    def vocabulary(self) -> PackVocabulary:
        """Return the component vocabulary derived from pack entity types."""
        return self._lexical.vocabulary

    @property
    def simulator_adapter_ids(self) -> tuple[str, ...]:
        """Return adapter ids this pack can run."""
        return self._lexical.simulator_adapter_ids

    @property
    def copilot_tools(self) -> tuple[CopilotToolSpec, ...]:
        """Return the pack-provided tools the copilot may call."""
        return self._lexical.copilot_tools

    @property
    def profile(self) -> DomainProfile:
        """Return the detection signals and entity types this pack handles."""
        return self._lexical.profile

    @property
    def catalog_entries(self) -> tuple[ComponentDetail, ...]:
        """Return the validated catalog entries this pack contributes."""
        return self._lexical.catalog_entries

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        """Score pack affinity: matched signals over the open-vocabulary tags."""
        return self._lexical.detect(tags)

    def resolve_part(self, ref: PartRef) -> PartResolution:
        """Resolve one part mention down the exact/family/category ladder."""
        return self._lexical.resolve_part(ref)

    @property
    def asset_registry_version(self) -> str | None:
        """Return the wired asset-registry version, or None when unwired."""
        return self._lexical.asset_registry_version

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        """Label modeled parts with the part name and visual outline."""
        base = self._lexical.render_spec(resolution)
        if resolution.asset_key is None or resolution.asset_key not in PART_VISUALS:
            return base
        entry = next(
            (
                candidate
                for candidate in self.catalog_entries
                if candidate.component_id == resolution.asset_key
            ),
            None,
        )
        if entry is None:  # pragma: no cover - visual keys mirror the catalog
            return base
        outline = PART_VISUALS[resolution.asset_key]["outline"]
        return base.model_copy(update={"label": entry.label, "fallback_package": outline})

    def procedural_spec(
        self, node_config: Mapping[str, Any], resolution: PartResolution
    ) -> tuple[ProceduralSpec, ...]:
        """Return the part assembly for one modeled part, or () otherwise."""
        if resolution.asset_key is None:
            return ()
        return VISUAL_SPECS.get(resolution.asset_key, ())

    def check_patch(
        self, graph: MethodologyGraph, patch: GraphPatch
    ) -> tuple[PackPreflightFinding, ...]:
        """Block saves that drop required interfaces or break composition."""
        return self._lexical.check_patch(graph, patch)

    def simulation_preview(self, graph: MethodologyGraph) -> SimulationPreview | None:
        """Return the wired builder's preview, or None when the pack offers none."""
        return self._lexical.simulation_preview(graph)

    def telemetry_mapping(self) -> TelemetryMapping | None:
        """Return None: no pack maps live telemetry yet (Stage 2)."""
        return self._lexical.telemetry_mapping()


pack = ElectronicsPack()

__all__ = ["pack"]
