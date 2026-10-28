"""Electronics domain pack: circuits, discretes, ICs, and measurement.

This is the Phase 2 launch pack: the catalog entries and detection
profile moved verbatim from the former core registry into pack data,
wired to the generic pack harness. No domain simulator is connected yet
(ngspice lands in Phase 5), so the pack honestly reports zero adapters.

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
from bizora.packs.lexical import LexicalPack

pack = LexicalPack(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    display=DISPLAY,
    signals=SIGNALS,
    threshold=THRESHOLD,
    entity_types=ENTITY_TYPES,
    catalog=COMPONENTS,
    simulator_adapter_ids=(),
    assets=AssetRegistry(AssetManifest(registry_version="1.0.0")),
)

__all__ = ["pack"]
