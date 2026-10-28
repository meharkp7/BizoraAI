"""Domain-agnostic detection and resolution engine.

Profiles describe research vocabularies in generic terms: weighted
detection signals plus the entity types each vocabulary understands.
Packs own every profile; this module only matches and routes, so it
names no domain, part, or paper.

Matching is deliberately lexical and explainable: every resolution
records the terms that grounded it, and anything unmatched resolves to
an explicit generic fallback instead of a fabricated part.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bizora.contracts.domain import (
    GENERIC_DOMAIN,
    DomainClassification,
    EntityResolution,
    InterfaceSpec,
    MissingInterface,
    ReplacementCompatibility,
)
from bizora.contracts.packs import DomainTag

if TYPE_CHECKING:
    from bizora.packs.base import PackRegistry


@dataclass(frozen=True)
class InterfaceDef:
    """An interface kind an entity type exposes."""

    name: str
    kind: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityTypeDef:
    """One resolvable entity type within a domain."""

    type_id: str
    display: str
    category: str
    match_terms: tuple[str, ...]
    interfaces: tuple[InterfaceDef, ...] = ()
    # Config keys whose values pin an exact identity (model numbers, ...).
    identity_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainProfile:
    """Detection signals and entity types for one research domain."""

    domain: str
    display: str
    signals: tuple[str, ...]
    entity_types: tuple[EntityTypeDef, ...] = ()
    fallback_category: str = "generic"
    # Minimum distinct signals before the domain wins over generic.
    threshold: int = 2


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into lowercase tokens, keeping hyphenated words whole."""
    return tuple(_TOKEN_RE.findall(text.lower()))


def extract_tags(*texts: str) -> tuple[DomainTag, ...]:
    """Build open-vocabulary tags from free text.

    Tags are word tokens plus adjacent bigrams (so multi-word signals
    still match), deduplicated in first-seen order. Until extraction
    produces model tags, the core derives these lexically from graph
    text; packs score affinity against them without any core vocabulary.
    """
    tokens: list[str] = []
    for text in texts:
        tokens.extend(tokenize(text))
    labels: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            labels.append(token)
    for left, right in zip(tokens, tokens[1:], strict=False):
        bigram = f"{left} {right}"
        if bigram not in seen:
            seen.add(bigram)
            labels.append(bigram)
    return tuple(DomainTag(label=label) for label in labels)


def match_terms(haystack: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    """Return the terms that occur in the haystack, in term order."""
    lowered = haystack.lower()
    return tuple(term for term in terms if term in lowered)


def _dedup_overlapping(matched: tuple[str, ...]) -> tuple[str, ...]:
    """Drop a term contained in another matched term.

    Without this, "cli" counts separately inside "client" and inflates
    the wrong candidate.
    """
    return tuple(
        term for term in matched if not any(other != term and term in other for other in matched)
    )


def _match_score(
    label_matched: tuple[str, ...], total_matched: tuple[str, ...]
) -> tuple[int, int, int, int]:
    """Rank candidates: label hits first, then longer (more specific) terms.

    The label names the node, so its matches outweigh description words
    ("coordinator ... client requests" is a coordinator, not a client).
    Longer terms win ties ("demodulat" beats "modulat" for Demodulator).
    """
    return (
        len(label_matched),
        max((len(term) for term in label_matched), default=0),
        len(total_matched),
        max((len(term) for term in total_matched), default=0),
    )


def _node_text(label: str, description: str | None, kind: str, config: object) -> str:
    parts = [label, kind]
    if description:
        parts.append(description)
    parts.append(repr(config))
    return " ".join(parts)


def detect_domain(
    title: str,
    brief_text: str,
    nodes: tuple[tuple[str, str | None, str, object], ...],
    registry: PackRegistry,
) -> DomainClassification:
    """Route graph text to the best pack, or fall back to explore-only.

    Graph text becomes open-vocabulary tags; the registry picks the
    highest-affinity pack. Unknown text routes to no pack and classifies
    as generic, never a guess.
    """
    haystack = " ".join(
        [title, brief_text]
        + [
            _node_text(label, description, kind, config)
            for label, description, kind, config in nodes
        ]
    )
    tags = extract_tags(haystack)
    pack = registry.route(tags)
    if pack is None:
        return DomainClassification(domain=GENERIC_DOMAIN, confidence=0.0, signals=())
    profile = getattr(pack, "profile", None)
    if profile is None:
        return DomainClassification(
            domain=pack.pack_id, confidence=pack.detect(tags), signals=()
        )
    matched = match_terms("\n".join(tag.label for tag in tags), profile.signals)
    confidence = round(len(matched) / (len(matched) + 2), 3) if matched else 0.0
    return DomainClassification(domain=profile.domain, confidence=confidence, signals=matched)


def _exact_identity(node_config: object, identity_keys: tuple[str, ...]) -> str | None:
    if not isinstance(node_config, dict) or not identity_keys:
        return None
    for key in identity_keys:
        value = node_config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return None


def resolve_node(
    profile: DomainProfile,
    node_id: str,
    label: str,
    description: str | None,
    kind: str,
    config: object,
) -> EntityResolution:
    """Resolve one node to the best entity type, or a generic fallback."""
    text = _node_text(label, description, kind, config)
    best: EntityTypeDef | None = None
    best_terms: tuple[str, ...] = ()
    best_score: tuple[int, int, int, int] = (-1, -1, -1, -1)
    for candidate in profile.entity_types:
        label_matched = _dedup_overlapping(match_terms(label.lower(), candidate.match_terms))
        total_matched = _dedup_overlapping(match_terms(text, candidate.match_terms))
        if not total_matched:
            continue
        score = _match_score(label_matched, total_matched)
        if score > best_score:
            best = candidate
            best_terms = total_matched
            best_score = score
    if best is None:
        return EntityResolution(
            node_id=node_id,
            domain=profile.domain,
            entity_type="generic-component",
            display_label=label,
            generic=True,
            category=profile.fallback_category,
            interfaces=(),
            matched_terms=(),
            confidence=0.0,
        )
    identity = _exact_identity(config, best.identity_keys)
    interfaces = tuple(
        InterfaceSpec(name=iface.name, kind=iface.kind, params=dict(iface.params))
        for iface in best.interfaces
    )
    confidence = min(0.5 + 0.25 * len(best_terms) + (0.25 if identity else 0.0), 1.0)
    # A matched type is an exact entity type even when the paper gives no
    # model number; only the unmatched fallback is a generic placeholder.
    return EntityResolution(
        node_id=node_id,
        domain=profile.domain,
        entity_type=best.type_id,
        display_label=identity or best.display,
        generic=False,
        category=best.category,
        interfaces=interfaces,
        matched_terms=best_terms,
        confidence=round(confidence, 3),
    )


def resolve_generic(node_id: str, label: str) -> EntityResolution:
    """Resolve a node when no domain matched: an honest unknown."""
    return EntityResolution(
        node_id=node_id,
        domain=GENERIC_DOMAIN,
        entity_type="generic-component",
        display_label=label,
        generic=True,
        category="generic",
        interfaces=(),
        matched_terms=(),
        confidence=0.0,
    )


def check_compatible(
    old: EntityResolution,
    new: EntityResolution,
    incident_edge_ids: tuple[str, ...],
) -> ReplacementCompatibility:
    """Report whether a replacement keeps its predecessor's interfaces.

    Unknown (generic) interfaces never conflict: only known kinds the
    replacement drops block the swap. Shared parameter keys must agree.
    """
    if old.generic or new.generic or not old.interfaces:
        return ReplacementCompatibility(compatible=True, incident_edge_ids=incident_edge_ids)
    new_by_kind = {iface.kind: iface for iface in new.interfaces}
    missing: list[MissingInterface] = []
    for iface in old.interfaces:
        replacement = new_by_kind.get(iface.kind)
        if replacement is None:
            missing.append(
                MissingInterface(
                    kind=iface.kind,
                    reason=f"Replacement {new.entity_type!r} exposes no {iface.kind!r} interface.",
                )
            )
            continue
        for key, value in iface.params.items():
            if key in replacement.params and replacement.params[key] != value:
                missing.append(
                    MissingInterface(
                        kind=iface.kind,
                        reason=(
                            f"Interface {iface.kind!r} parameter {key!r} changes "
                            f"from {value!r} to {replacement.params[key]!r}."
                        ),
                    )
                )
    return ReplacementCompatibility(
        compatible=not missing,
        missing_interfaces=tuple(missing),
        incident_edge_ids=incident_edge_ids,
    )
