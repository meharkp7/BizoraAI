"""Domain packs: interface, registry, and the default pack set."""

from bizora.packs import (
    deep_learning,
    distributed_systems,
    electronics,
    iot,
    quantization,
    signal_processing,
)
from bizora.packs.base import DomainPack, PackRegistry, ProceduralMeshPack, ProfiledPack
from bizora.packs.lexical import LexicalPack


def default_registry() -> PackRegistry:
    """Return a registry with every built-in pack, in routing order.

    Registration order breaks affinity ties, so it stays fixed.
    """
    return PackRegistry(
        [
            electronics.pack,
            iot.pack,
            quantization.pack,
            signal_processing.pack,
            distributed_systems.pack,
            deep_learning.pack,
        ]
    )


__all__ = [
    "DomainPack",
    "LexicalPack",
    "PackRegistry",
    "ProceduralMeshPack",
    "ProfiledPack",
    "default_registry",
]
