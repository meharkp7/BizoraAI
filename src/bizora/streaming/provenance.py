"""Honesty labels for visual run elements (Phase 7, R8).

Every animation and visual in the workspace carries one
:class:`VisualProvenance`: ``measured`` (observed from a real run),
``assumed`` (depends on an unverified assumption), or ``illustrative``
(a placeholder or stand-in). This module centralizes the mapping from
existing groundings (result kinds, assumed flags, illustrative flags)
so backend and frontend label identically.
"""

from bizora.contracts.experiment import ResultKind
from bizora.contracts.streaming import VisualProvenance

_LABELS: dict[VisualProvenance, str] = {
    VisualProvenance.MEASURED: "Measured",
    VisualProvenance.ASSUMED: "Assumed",
    VisualProvenance.ILLUSTRATIVE: "Illustrative",
}

_DESCRIPTIONS: dict[VisualProvenance, str] = {
    VisualProvenance.MEASURED: "Observed from a real run.",
    VisualProvenance.ASSUMED: "Depends on an unverified assumption.",
    VisualProvenance.ILLUSTRATIVE: "A placeholder or stand-in, not observed data.",
}


def resolve_visual_provenance(
    *,
    result_kind: ResultKind | None = None,
    assumed: bool = False,
    illustrative: bool = False,
) -> VisualProvenance:
    """Resolve the honesty label from existing grounding signals.

    Precedence is deliberate: an illustrative stand-in stays
    illustrative even when it also carries assumptions, and anything
    assumed (or not measured) is never labelled measured.
    """
    if illustrative:
        return VisualProvenance.ILLUSTRATIVE
    if assumed:
        return VisualProvenance.ASSUMED
    if result_kind is not None and result_kind != ResultKind.MEASURED:
        return VisualProvenance.ASSUMED
    return VisualProvenance.MEASURED


def provenance_label(provenance: VisualProvenance) -> str:
    """Return the short badge text for a provenance label."""
    return _LABELS[provenance]


def provenance_description(provenance: VisualProvenance) -> str:
    """Return the tooltip text for a provenance label."""
    return _DESCRIPTIONS[provenance]
