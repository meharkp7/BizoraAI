"""Tests for telemetry streaming contracts and event builders."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bizora.contracts.run import RunState
from bizora.contracts.streaming import (
    ComparisonWithPaperReport,
    PaperReportedMetric,
    ReportedComparisonRow,
    TelemetryEvent,
    TelemetryEventKind,
    TelemetryLogLevel,
    VisualProvenance,
)
from bizora.streaming import events


def test_step_event_builder_marks_progress() -> None:
    """Step events carry their index, label, and total."""
    event = events.make_step_event("run-1", 0, 3, label="epoch", total_steps=10)
    assert event.kind == TelemetryEventKind.STEP
    assert event.step is not None
    assert event.step.step_index == 3
    assert event.step.total_steps == 10
    assert event.provenance == VisualProvenance.MEASURED


def test_step_event_rejects_index_past_total() -> None:
    """A step index at or past the total is invalid."""
    with pytest.raises(ValidationError):
        events.make_step_event("run-1", 0, 10, total_steps=10)


def test_metric_event_rejects_non_finite_values() -> None:
    """Live metric samples must be finite to drive charts."""
    with pytest.raises(ValidationError):
        events.make_metric_event("run-1", 0, "m-1", "loss", float("nan"))
    with pytest.raises(ValidationError):
        events.make_metric_event("run-1", 0, "m-1", "loss", float("inf"))


def test_log_event_carries_level_and_message() -> None:
    """Log events preserve severity and text."""
    event = events.make_log_event("run-1", 1, TelemetryLogLevel.WARNING, "slow step", step_index=4)
    assert event.kind == TelemetryEventKind.LOG
    assert event.log is not None
    assert event.log.level == TelemetryLogLevel.WARNING
    assert event.log.step_index == 4


def test_pack_signal_accepts_free_vocabulary() -> None:
    """Pack signals take any signal id: no vocabulary is enumerated."""
    event = events.make_pack_signal_event(
        "run-1",
        2,
        "unseen-pack/unseen-signal",
        "Unseen Signal",
        [0.1, 0.2],
        unit="V",
        node_ids=["node-a"],
    )
    assert event.pack_signal is not None
    assert event.pack_signal.values == (0.1, 0.2)
    assert event.pack_signal.node_ids == ("node-a",)


def test_pack_signal_rejects_empty_and_non_finite() -> None:
    """Signals need at least one finite sample."""
    with pytest.raises(ValidationError):
        events.make_pack_signal_event("run-1", 0, "s", "S", [])
    with pytest.raises(ValidationError):
        events.make_pack_signal_event("run-1", 0, "s", "S", [float("nan")])


def test_state_event_restricts_error_text() -> None:
    """Only failed/cancelled states may carry error text."""
    event = events.make_state_event("run-1", 9, RunState.SUCCEEDED)
    assert event.state is not None
    assert event.state.state == RunState.SUCCEEDED
    with pytest.raises(ValidationError):
        events.make_state_event("run-1", 9, RunState.RUNNING, error="boom")


def test_envelope_requires_matching_payload() -> None:
    """The envelope rejects missing or mismatched payloads."""
    stamp = datetime.now(UTC)
    with pytest.raises(ValidationError):
        TelemetryEvent(
            run_id="run-1",
            seq=0,
            emitted_at=stamp,
            kind=TelemetryEventKind.METRIC,
        )
    metric = events.make_metric_event("run-1", 0, "m-1", "loss", 0.5).metric
    assert metric is not None
    with pytest.raises(ValidationError):
        TelemetryEvent(
            run_id="run-1",
            seq=0,
            emitted_at=stamp,
            kind=TelemetryEventKind.STEP,
            metric=metric,
        )


def test_paper_reported_metric_requires_evidence() -> None:
    """Reported numbers without any grounding pointer are rejected."""
    with pytest.raises(ValidationError):
        PaperReportedMetric(name="accuracy", raw_value="92%", source_id="paper-1")
    grounded = PaperReportedMetric(
        name="accuracy",
        raw_value="92%",
        value=0.92,
        source_id="paper-1",
        table_id="table-1",
        page=4,
    )
    assert grounded.value == 0.92


def test_reported_row_rejects_misfiled_entries() -> None:
    """Rows only group reported entries under their own metric name."""
    entry = PaperReportedMetric(name="other", raw_value="1", source_id="paper-1", page=1)
    with pytest.raises(ValidationError):
        ReportedComparisonRow(
            name="accuracy",
            baseline_measured=0.9,
            variant_measured=0.91,
            reported=(entry,),
        )


def test_comparison_view_requires_exact_coverage() -> None:
    """Rows must cover every measured and reported name exactly once."""
    from bizora.contracts.comparison import (
        ComparisonVerdict,
        GraphPair,
        MetricComparison,
        RunComparison,
    )

    comparison = RunComparison(
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
                variant_value=0.91,
                absolute_change=0.01,
                relative_change=0.01 / 0.9,
            ),
        ),
    )
    entry = PaperReportedMetric(name="accuracy", raw_value="0.89", source_id="paper-1", page=2)
    view = ComparisonWithPaperReport(
        comparison=comparison,
        reported=(entry,),
        rows=(
            ReportedComparisonRow(
                name="accuracy",
                baseline_measured=0.9,
                variant_measured=0.91,
                reported=(entry,),
            ),
        ),
    )
    assert view.rows[0].reported == (entry,)
    with pytest.raises(ValidationError):
        ComparisonWithPaperReport(comparison=comparison, reported=(entry,), rows=())
