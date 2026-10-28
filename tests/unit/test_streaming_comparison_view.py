"""Tests for the measured-vs-paper-reported comparison view."""

from bizora.contracts.comparison import (
    ComparisonVerdict,
    GraphPair,
    MetricComparison,
    RunComparison,
)
from bizora.contracts.streaming import PaperReportedMetric
from bizora.streaming.comparison_view import (
    attach_paper_report,
    build_reported_rows,
)


def make_comparison() -> RunComparison:
    """Build a minimal valid measured comparison."""
    return RunComparison(
        baseline_run_id="run-a",
        variant_run_id="run-b",
        verdict=ComparisonVerdict.VALID,
        reasons=(),
        graph=GraphPair(
            baseline_graph_id="g",
            baseline_graph_version=1,
            variant_graph_id="g",
            variant_graph_version=2,
        ),
        metrics=(
            MetricComparison(
                name="accuracy",
                baseline_value=0.9,
                variant_value=0.92,
                absolute_change=0.02,
                relative_change=0.02 / 0.9,
            ),
        ),
    )


def make_reported(name: str, raw_value: str) -> PaperReportedMetric:
    """Build a grounded paper-reported entry (free metric names)."""
    return PaperReportedMetric(
        name=name,
        raw_value=raw_value,
        source_id="paper-1",
        table_id="table-1",
        page=4,
    )


def test_rows_join_measured_and_reported_by_exact_name() -> None:
    """Matching names share a row; measured and reported stay separate."""
    rows = build_reported_rows(make_comparison(), [make_reported("accuracy", "91%")])
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "accuracy"
    assert row.baseline_measured == 0.9
    assert row.variant_measured == 0.92
    assert len(row.reported) == 1
    assert row.reported[0].raw_value == "91%"


def test_rows_cover_reported_only_names() -> None:
    """Paper numbers without measured pairs still appear, measured empty."""
    rows = build_reported_rows(make_comparison(), [make_reported("latency", "3ms")])
    assert [row.name for row in rows] == ["accuracy", "latency"]
    latency = rows[1]
    assert latency.baseline_measured is None
    assert latency.variant_measured is None
    assert len(latency.reported) == 1


def test_name_matching_is_exact() -> None:
    """Differently-cased names never merge (no fuzzy vocabulary)."""
    rows = build_reported_rows(make_comparison(), [make_reported("Accuracy", "91%")])
    assert [row.name for row in rows] == ["Accuracy", "accuracy"]
    assert rows[0].baseline_measured is None


def test_multiple_reports_group_under_one_row() -> None:
    """Several paper entries for one metric share its row."""
    rows = build_reported_rows(
        make_comparison(),
        [make_reported("accuracy", "91%"), make_reported("accuracy", "0.91")],
    )
    assert len(rows) == 1
    assert len(rows[0].reported) == 2


def test_attach_builds_valid_view() -> None:
    """The attached view carries comparison, reports, and rows."""
    comparison = make_comparison()
    view = attach_paper_report(comparison, [make_reported("accuracy", "91%")])
    assert view.comparison == comparison
    assert len(view.reported) == 1
    assert [row.name for row in view.rows] == ["accuracy"]
