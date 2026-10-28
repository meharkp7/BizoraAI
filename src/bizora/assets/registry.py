"""Versioned 3D asset registry: data-driven lookup, no part logic.

The registry is built from an AssetManifest (data) and answers three
index lookups: exact model key, manufacturer family, and package. All
matching is normalized text comparison; part names, manufacturers, and
packages live in the manifest data, never in this logic.
"""

from __future__ import annotations

from bizora.contracts.assets import AssetManifest, AssetRecord, normalize_asset_token


class AssetRegistry:
    """Index one manifest snapshot for the resolver ladder."""

    def __init__(self, manifest: AssetManifest) -> None:
        self._manifest = manifest
        self._by_key: dict[str, AssetRecord] = {}
        self._by_family: dict[tuple[str, str], tuple[AssetRecord, ...]] = {}
        self._by_package: dict[str, tuple[AssetRecord, ...]] = {}
        family_groups: dict[tuple[str, str], list[AssetRecord]] = {}
        package_groups: dict[str, list[AssetRecord]] = {}
        for asset in manifest.assets:
            self._by_key[normalize_asset_token(asset.model_key)] = asset
            if asset.manufacturer and asset.family:
                key = (
                    normalize_asset_token(asset.manufacturer),
                    normalize_asset_token(asset.family),
                )
                family_groups.setdefault(key, []).append(asset)
            if asset.package:
                package_groups.setdefault(normalize_asset_token(asset.package), []).append(asset)
        for family_key, family_group in family_groups.items():
            self._by_family[family_key] = tuple(family_group)
        for package_key, package_group in package_groups.items():
            self._by_package[package_key] = tuple(package_group)

    @property
    def version(self) -> str:
        """Return the registry snapshot version this index was built from."""
        return self._manifest.registry_version

    @property
    def manifest(self) -> AssetManifest:
        """Return the manifest snapshot backing this registry."""
        return self._manifest

    def __len__(self) -> int:
        return len(self._manifest.assets)

    def get(self, model_key: str) -> AssetRecord | None:
        """Return the exact record for one model key, or None."""
        return self._by_key.get(normalize_asset_token(model_key))

    def by_family(self, manufacturer: str, family: str) -> tuple[AssetRecord, ...]:
        """Return every record sharing one manufacturer family, in order."""
        key = (normalize_asset_token(manufacturer), normalize_asset_token(family))
        return self._by_family.get(key, ())

    def by_package(self, package: str) -> tuple[AssetRecord, ...]:
        """Return every record sharing one package id, in order."""
        return self._by_package.get(normalize_asset_token(package), ())

    def manufacturers(self) -> tuple[str, ...]:
        """Return the distinct manufacturers present, sorted."""
        makers = {
            normalize_asset_token(asset.manufacturer)
            for asset in self._manifest.assets
            if asset.manufacturer
        }
        return tuple(sorted(makers))

    def packages(self) -> tuple[str, ...]:
        """Return the distinct package ids present, sorted."""
        packages = {
            normalize_asset_token(asset.package) for asset in self._manifest.assets if asset.package
        }
        return tuple(sorted(packages))
