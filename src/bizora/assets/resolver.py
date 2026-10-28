"""Asset resolver ladder: exact model, family, package, primitive.

Each rung is generic normalized-text matching over registry data plus
the package-dimension table. Nothing here names a part, manufacturer,
or package; those live in the manifest and the data file. When no rung
matches, the query stays UNRESOLVED with a reason instead of a guess.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from bizora.assets.registry import AssetRegistry
from bizora.contracts.assets import (
    AssetLevel,
    AssetProvenance,
    AssetQuery,
    ProceduralSpec,
    ResolvedAsset,
    normalize_asset_token,
)


@lru_cache(maxsize=1)
def _package_table() -> dict[str, dict[str, Any]]:
    """Load the generic package-dimension table shipped as asset data."""
    data_path = resources.files("bizora.assets") / "data" / "packages.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    table: dict[str, dict[str, Any]] = {}
    for entry in payload.get("packages", []):
        package = entry.get("package")
        if isinstance(package, str) and package.strip():
            table[normalize_asset_token(package)] = entry
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    table.setdefault(normalize_asset_token(alias), entry)
    return table


def _lookup_variant(token: str) -> dict[str, Any] | None:
    """Return the table entry for one normalized variant token, if any."""
    return _package_table().get(token)


def package_spec(package: str) -> ProceduralSpec | None:
    """Return the procedural spec for one package id, or None if unknown.

    Multi-variant values ("PDIP-8 / SOIC-8") try each alternative in
    order and use the first covered variant; aliases ("0603") map to
    their rows. Anything else stays unknown instead of a guess.
    """
    token = normalize_asset_token(package)
    entry = _lookup_variant(token)
    if entry is None:
        for variant in token.split("/"):
            entry = _lookup_variant(normalize_asset_token(variant))
            if entry is not None:
                break
    if entry is None:
        return None
    return ProceduralSpec.model_validate(
        {
            "kind": entry["kind"],
            "body_length_mm": entry["body_length_mm"],
            "body_width_mm": entry["body_width_mm"],
            "body_height_mm": entry["body_height_mm"],
            "pin_count": entry["pin_count"],
            "pin_pitch_mm": entry["pin_pitch_mm"],
            "pin_rows": entry["pin_rows"],
            "pin_length_mm": entry["pin_length_mm"],
        }
    )


def known_packages() -> tuple[str, ...]:
    """Return the package ids the dimension table covers, sorted."""
    return tuple(sorted(_package_table()))


def _describe(query: AssetQuery) -> str:
    bits = []
    if query.model_key:
        bits.append(f"model {query.model_key!r}")
    if query.manufacturer or query.family:
        bits.append(f"family {query.manufacturer or '?'}/{query.family or '?'}")
    if query.package:
        bits.append(f"package {query.package!r}")
    return ", ".join(bits) if bits else "an empty query"


def resolve_asset(registry: AssetRegistry, query: AssetQuery) -> ResolvedAsset:
    """Walk the ladder; miss every rung and the query stays unresolved."""
    if query.model_key:
        exact = registry.get(query.model_key)
        if exact is not None:
            return ResolvedAsset(
                level=AssetLevel.EXACT,
                provenance=exact.provenance,
                asset=exact,
                reason=f"Exact model-key match on {exact.model_key!r}.",
            )
    if query.manufacturer and query.family:
        family = registry.by_family(query.manufacturer, query.family)
        if family:
            first = family[0]
            return ResolvedAsset(
                level=AssetLevel.FAMILY,
                provenance=AssetProvenance.ILLUSTRATIVE,
                asset=first,
                reason=(
                    f"No exact model for {_describe(query)}; "
                    f"using family representative {first.model_key!r} as illustrative."
                ),
            )
    if query.package:
        packaged = registry.by_package(query.package)
        if packaged:
            first = packaged[0]
            return ResolvedAsset(
                level=AssetLevel.PACKAGE,
                provenance=AssetProvenance.ILLUSTRATIVE,
                asset=first,
                reason=(
                    f"No exact or family model for {_describe(query)}; "
                    f"using package representative {first.model_key!r} as illustrative."
                ),
            )
        spec = package_spec(query.package)
        if spec is not None:
            return ResolvedAsset(
                level=AssetLevel.PRIMITIVE,
                provenance=AssetProvenance.ILLUSTRATIVE,
                procedural=spec,
                reason=(
                    f"No registry model for {_describe(query)}; "
                    f"generated a parametric {spec.kind.value} from package dimensions."
                ),
            )
    return ResolvedAsset(
        level=AssetLevel.UNRESOLVED,
        provenance=AssetProvenance.ILLUSTRATIVE,
        reason=(
            f"No registry entry or package dimensions match {_describe(query)}; "
            "leaving the part without a visual."
        ),
    )
