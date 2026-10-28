"""Domain-pack interface: the generality mechanism from the build brief.

The core stays domain-agnostic. Each domain ships as a pack behind this
Protocol: affinity detection over open-vocabulary tags, a data-driven
vocabulary, part resolution, render specs, simulator adapters, patch
preflight rules, and copilot tools. Routing picks the best pack or
returns None so the caller can fall back to explore-only mode.
"""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bizora.contracts.assets import ProceduralSpec
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
)
from bizora.contracts.patches import GraphPatch

if TYPE_CHECKING:
    from bizora.contracts.components import ComponentDetail
    from bizora.core.entity_registry import DomainProfile


@runtime_checkable
class DomainPack(Protocol):
    """Interface every domain pack implements."""

    @property
    def pack_id(self) -> str:
        """Return the stable pack identifier."""
        ...

    @property
    def pack_version(self) -> str:
        """Return the exact pack version."""
        ...

    @property
    def vocabulary(self) -> PackVocabulary:
        """Return the data-driven component vocabulary this pack handles."""
        ...

    @property
    def simulator_adapter_ids(self) -> tuple[str, ...]:
        """Return adapter ids (see the adapter registry) this pack can run."""
        ...

    @property
    def copilot_tools(self) -> tuple[CopilotToolSpec, ...]:
        """Return the pack-provided tools the copilot may call."""
        ...

    def detect(self, tags: tuple[DomainTag, ...]) -> float:
        """Return this pack's affinity for the tags (0 means cannot handle)."""
        ...

    def resolve_part(self, ref: PartRef) -> PartResolution:
        """Resolve one part mention down the exact/family/category ladder."""
        ...

    def render_spec(self, resolution: PartResolution) -> RenderSpec:
        """Return the 3D render spec for one resolved part."""
        ...

    def check_patch(
        self, graph: MethodologyGraph, patch: GraphPatch
    ) -> tuple[PackPreflightFinding, ...]:
        """Return pack-rule findings for a proposed edit; empty means clear."""
        ...

    def simulation_preview(self, graph: MethodologyGraph) -> SimulationPreview | None:
        """Return what this pack would simulate, or None when it offers none."""
        ...


@runtime_checkable
class ProfiledPack(Protocol):
    """A pack that also exposes lexical detection data and catalog entries.

    The core routing engine consumes this structurally: detection signals
    and entity types drive classification and resolution, catalog entries
    feed the component library. All of it is pack-owned data; the core
    only matches and routes. Packs without a profile (like the toy pack)
    still route, but resolve to generic placeholders.
    """

    @property
    def profile(self) -> "DomainProfile":
        """Return the detection signals and entity types this pack handles."""
        ...

    @property
    def catalog_entries(self) -> "tuple[ComponentDetail, ...]":
        """Return the validated catalog entries this pack contributes."""
        ...


@runtime_checkable
class ProceduralMeshPack(Protocol):
    """A pack that derives fallback geometry from node config.

    The core calls this before the generic package path, so packs
    that know the exact part render their own solids first and packs
    without config-driven geometry simply return (). Returned specs
    must be honest parameters for the shared mesh builder (real
    dimensions where the config states them, documented defaults
    otherwise), never decoration.
    """

    def procedural_spec(
        self, node_config: Mapping[str, Any], resolution: PartResolution
    ) -> tuple[ProceduralSpec, ...]:
        """Return placed solids for one node, or () when it has none."""
        ...


class PackRegistry:
    """Register packs and route open-vocabulary domain tags to the best one."""

    def __init__(self, packs: Iterable[DomainPack] = ()) -> None:
        self._packs: dict[str, DomainPack] = {}
        for pack in packs:
            self.register(pack)

    def register(self, pack: DomainPack) -> None:
        """Add a pack; duplicate registrations are wiring bugs."""
        if pack.pack_id in self._packs:
            raise ValueError(f"Pack '{pack.pack_id}' is already registered.")
        self._packs[pack.pack_id] = pack

    def get(self, pack_id: str) -> DomainPack | None:
        """Return one pack by id, or None when unknown."""
        return self._packs.get(pack_id)

    def available(self) -> tuple[tuple[str, str], ...]:
        """Return the registered (pack_id, pack_version) pairs."""
        return tuple(sorted((pack.pack_id, pack.pack_version) for pack in self._packs.values()))

    @property
    def packs(self) -> tuple[DomainPack, ...]:
        """Return the registered packs in registration order."""
        return tuple(self._packs.values())

    def route(self, tags: tuple[DomainTag, ...]) -> DomainPack | None:
        """Return the highest-affinity pack, or None for explore-only mode.

        Ties resolve to the first registered pack. Empty tags, or zero
        affinity everywhere, mean no pack claims the graph.
        """
        best: DomainPack | None = None
        best_score = 0.0
        for pack in self._packs.values():
            score = pack.detect(tags)
            if score > best_score:
                best = pack
                best_score = score
        return best
