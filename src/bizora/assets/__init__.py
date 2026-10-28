"""3D asset pipeline: versioned registry, resolver ladder, fallbacks."""

from bizora.assets.procedural import build_assembly, build_mesh
from bizora.assets.registry import AssetRegistry
from bizora.assets.resolver import known_packages, package_spec, resolve_asset

__all__ = [
    "AssetRegistry",
    "build_assembly",
    "build_mesh",
    "known_packages",
    "package_spec",
    "resolve_asset",
]
