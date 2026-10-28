"""Measured-vs-paper-reported comparison view (Phase 7, R7).

The existing :class:`RunComparison` compares measured metrics across two
runs. This view adds the paper's own reported numbers alongside, keeping
the two sources structurally separate: measured values come from the
comparison, reported values from evidence-grounded
:class:`PaperReportedMetric` entries. Name matching is exact
(case-sensitive) so unrelated metrics are never merged by fuzzy
similarity; metric names are free text (Rule Zero), not a vocabulary.
"""

from collections.abc import Sequence

from bizora.contracts.comparison import RunComparison
from bizora.contracts.streaming import (
    ComparisonWithPaperReport,
    PaperReportedMetric,
    ReportedComparisonRow,
)


def build_reported_rows(
    comparison: RunComparison,
    reported: Sequence[PaperReportedMetric],
) -> tuple[ReportedComparisonRow, ...]:
    """Join measured pairs with paper-reported entries by exact name."""
    measured = {metric.name: metric for metric in comparison.metrics}
    by_name: dict[str, list[PaperReportedMetric]] = {}
    for entry in reported:
        by_name.setdefault(entry.name, []).append(entry)
    rows: list[ReportedComparisonRow] = []
    for name in sorted(set(measured) | set(by_name)):
        pair = measured.get(name)
        rows.append(
            ReportedComparisonRow(
                name=name,
                baseline_measured=pair.baseline_value if pair else None,
                variant_measured=pair.variant_value if pair else None,
                reported=tuple(by_name.get(name, ())),
            )
        )
    return tuple(rows)


def attach_paper_report(
    comparison: RunComparison,
    reported: Sequence[PaperReportedMetric],
) -> ComparisonWithPaperReport:
    """Build the full view: measured comparison plus reported rows."""
    entries = tuple(reported)
    return ComparisonWithPaperReport(
        comparison=comparison,
        reported=entries,
        rows=build_reported_rows(comparison, entries),
    )
