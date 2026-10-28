"""Electronics domain pack: circuits, discretes, ICs, and measurement.

This is the Phase 2 launch pack: the catalog entries and detection
profile moved verbatim from the former core registry into pack data,
wired to the generic pack harness. Phase 5 connected the local ngspice
adapter plus a netlist/BOM/preflight simulation preview.

Phase 4 wires an asset registry for 3D render specs. No measured model
bytes exist yet (fetching real corpora needs license verification, so
no downloads happen here), and the registry therefore starts empty:
every render spec stays illustrative until verified models land.
"""

from bizora.assets.registry import AssetRegistry
from bizora.contracts.assets import AssetManifest
from bizora.packs.electronics.data import (
    COMPONENTS,
    DISPLAY,
    ENTITY_TYPES,
    PACK_ID,
    PACK_VERSION,
    SIGNALS,
    THRESHOLD,
)
from bizora.packs.electronics.preview import build_preview
from bizora.packs.lexical import LexicalPack

pack = LexicalPack(
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

__all__ = ["pack"]
