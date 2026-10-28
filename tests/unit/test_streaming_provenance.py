"""Tests for visual honesty labels (measured/assumed/illustrative)."""

from bizora.contracts.experiment import ResultKind
from bizora.contracts.streaming import VisualProvenance
from bizora.streaming.provenance import (
    provenance_description,
    provenance_label,
    resolve_visual_provenance,
)


def test_default_is_measured() -> None:
    """Real run observations with no caveats are measured."""
    assert resolve_visual_provenance() == VisualProvenance.MEASURED
    assert resolve_visual_provenance(result_kind=ResultKind.MEASURED) == VisualProvenance.MEASURED


def test_illustrative_wins_over_everything() -> None:
    """A stand-in is never labelled measured, even when assumed."""
    assert (
        resolve_visual_provenance(illustrative=True, assumed=True) == VisualProvenance.ILLUSTRATIVE
    )
    assert (
        resolve_visual_provenance(illustrative=True, result_kind=ResultKind.MEASURED)
        == VisualProvenance.ILLUSTRATIVE
    )


def test_assumed_covers_flags_and_estimates() -> None:
    """Assumed flags and non-measured result kinds map to assumed."""
    assert resolve_visual_provenance(assumed=True) == VisualProvenance.ASSUMED
    assert resolve_visual_provenance(result_kind=ResultKind.ESTIMATED) == VisualProvenance.ASSUMED
    assert resolve_visual_provenance(result_kind=ResultKind.HYPOTHESIS) == VisualProvenance.ASSUMED


def test_labels_and_descriptions_cover_all_cases() -> None:
    """Every provenance has badge text and a tooltip."""
    assert provenance_label(VisualProvenance.MEASURED) == "Measured"
    assert provenance_label(VisualProvenance.ASSUMED) == "Assumed"
    assert provenance_label(VisualProvenance.ILLUSTRATIVE) == "Illustrative"
    for provenance in VisualProvenance:
        assert provenance_description(provenance)
