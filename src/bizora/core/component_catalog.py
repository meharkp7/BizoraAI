"""Component catalog: validated in-memory registry with search.

Entries live as data in the domain packs and are validated into
ComponentDetail contracts at pack construction, so a malformed entry
fails fast instead of shipping a broken library card. This module only
concatenates pack entries in registry order and checks that each one
links to a real pack vocabulary.
"""

from __future__ import annotations

from bizora.contracts.components import ComponentDetail, ComponentSummary
from bizora.contracts.graph import NodeKind
from bizora.packs import ProfiledPack, default_registry


def _load(
    details: tuple[ComponentDetail, ...], known: dict[str, frozenset[str]]
) -> dict[str, ComponentDetail]:
    catalog: dict[str, ComponentDetail] = {}
    for detail in details:
        if detail.component_id in catalog:
            raise ValueError(f"Duplicate component id {detail.component_id!r}.")
        known_types = known.get(detail.domain)
        if known_types is None:
            raise ValueError(f"Component {detail.component_id!r} names unknown domain.")
        if detail.entity_type not in known_types:
            raise ValueError(
                f"Component {detail.component_id!r} names unknown entity type "
                f"{detail.entity_type!r} for domain {detail.domain!r}."
            )
        if not detail.generic and not detail.part_number:
            raise ValueError(f"Exact component {detail.component_id!r} needs a part number.")
        if detail.kind not in {kind.value for kind in NodeKind}:
            raise ValueError(f"Component {detail.component_id!r} names unknown node kind.")
        catalog[detail.component_id] = detail
    return catalog


def _collect() -> tuple[tuple[ComponentDetail, ...], dict[str, frozenset[str]]]:
    """Gather pack entries and vocabularies in registry order."""
    details: list[ComponentDetail] = []
    known: dict[str, frozenset[str]] = {}
    for pack in default_registry().packs:
        if not isinstance(pack, ProfiledPack):
            continue
        known[pack.pack_id] = frozenset(
            entity.type_id for entity in pack.profile.entity_types
        )
        details.extend(pack.catalog_entries)
    return tuple(details), known


CATALOG: dict[str, ComponentDetail] = _load(*_collect())


def get_component(component_id: str) -> ComponentDetail | None:
    """Return one catalog entry by exact id, or None."""
    return CATALOG.get(component_id)


def summarize(detail: ComponentDetail) -> ComponentSummary:
    """Project a full entry down to its searchable identity card."""
    return ComponentSummary(
        component_id=detail.component_id,
        domain=detail.domain,
        entity_type=detail.entity_type,
        category=detail.category,
        kind=detail.kind,
        label=detail.label,
        generic=detail.generic,
        manufacturer=detail.manufacturer,
        part_number=detail.part_number,
        headline=detail.headline,
    )


def _score(detail: ComponentDetail, tokens: tuple[str, ...]) -> int:
    """Rank entries: id and part-number hits first, then label, then text."""
    component_id = detail.component_id.lower()
    part = (detail.part_number or "").lower()
    label = detail.label.lower()
    haystack = " ".join(
        [
            detail.label,
            detail.headline,
            detail.description,
            detail.manufacturer or "",
            detail.part_number or "",
            detail.entity_type,
            detail.category,
            " ".join(spec.name for spec in detail.specs),
        ]
    ).lower()
    score = 0
    for token in tokens:
        if token in component_id or (part and token in part):
            score += 6
        elif token in label:
            score += 4
        elif token in haystack:
            score += 1
        else:
            return 0
    if not detail.generic:
        score += 1
    return score


def search_components(
    query: str = "",
    *,
    domain: str | None = None,
    category: str | None = None,
    generic: bool | None = None,
    limit: int = 50,
) -> tuple[ComponentSummary, ...]:
    """Search the catalog with optional domain/category/identity filters."""
    tokens = tuple(token for token in query.lower().split() if token)
    ranked: list[tuple[int, ComponentDetail]] = []
    for detail in CATALOG.values():
        if domain is not None and detail.domain != domain:
            continue
        if category is not None and detail.category != category:
            continue
        if generic is not None and detail.generic != generic:
            continue
        score = _score(detail, tokens) if tokens else 1
        if score > 0:
            ranked.append((score, detail))
    ranked.sort(key=lambda item: (-item[0], item[1].label))
    return tuple(summarize(detail) for _, detail in ranked[: max(limit, 1)])


def list_domains() -> tuple[str, ...]:
    """Return catalog domains in first-seen order."""
    seen: list[str] = []
    for detail in CATALOG.values():
        if detail.domain not in seen:
            seen.append(detail.domain)
    return tuple(seen)


def list_categories(domain: str | None = None) -> tuple[str, ...]:
    """Return catalog categories, optionally scoped to one domain."""
    seen: list[str] = []
    for detail in CATALOG.values():
        if domain is not None and detail.domain != domain:
            continue
        if detail.category not in seen:
            seen.append(detail.category)
    return tuple(seen)
