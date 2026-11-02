"""Tests for copilot run-card honesty: only measured runs earn the label."""

from datetime import UTC, datetime

from tests.unit.test_run_api import make_config_payload, make_graph_payload

from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.run import ExperimentRun, MetricRecord, RunState
from bizora.copilot import service as copilot_service
from bizora.copilot.citations import RunCitation
from bizora.copilot.tools import CopilotContext


def _run(state: RunState, run_id: str = "run-1") -> ExperimentRun:
    """Build a run in the given lifecycle state."""
    created = datetime(2026, 1, 1, tzinfo=UTC)
    started = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC)
    return ExperimentRun(
        run_id=run_id,
        config=ExperimentConfig.model_validate(make_config_payload()),
        state=state,
        created_at=created,
        started_at=started if state != RunState.PENDING else None,
        finished_at=finished if state not in (RunState.PENDING, RunState.RUNNING) else None,
        error="boom" if state == RunState.FAILED else None,
    )


def _context(
    run: ExperimentRun | None, metrics: tuple[MetricRecord, ...] = ()
) -> CopilotContext:
    """Build a context exposing one run and its metrics."""
    graph = MethodologyGraph.model_validate(make_graph_payload())
    runs = [run] if run is not None else []
    return CopilotContext(
        graph=graph,
        list_runs=lambda: runs,
        list_metrics=lambda _run_id: list(metrics),
    )


def _metric(run_id: str = "run-1", name: str = "accuracy") -> MetricRecord:
    """Build one recorded metric value."""
    return MetricRecord(
        metric_id="metric-1",
        run_id=run_id,
        name=name,
        value=0.9,
        result_kind=ResultKind.MEASURED,
    )


def test_run_card_labels_succeeded_run_with_value_measured() -> None:
    context = _context(_run(RunState.SUCCEEDED), (_metric(),))
    citation = RunCitation(run_id="run-1", metric_name="accuracy")

    card = copilot_service._run_card(citation, context)

    assert card.title == "Measured run"
    assert "Metric: accuracy = 0.9" in card.body


def test_run_card_labels_succeeded_run_without_metric_measured() -> None:
    context = _context(_run(RunState.SUCCEEDED))
    citation = RunCitation(run_id="run-1")

    card = copilot_service._run_card(citation, context)

    assert card.title == "Measured run"


def test_run_card_labels_failed_run_unmeasured() -> None:
    context = _context(_run(RunState.FAILED), (_metric(),))
    citation = RunCitation(run_id="run-1", metric_name="accuracy")

    card = copilot_service._run_card(citation, context)

    assert card.title == "Unmeasured run"
    assert "State: failed" in card.body


def test_run_card_labels_missing_metric_unmeasured() -> None:
    context = _context(_run(RunState.SUCCEEDED))
    citation = RunCitation(run_id="run-1", metric_name="accuracy")

    card = copilot_service._run_card(citation, context)

    assert card.title == "Unmeasured run"
    assert "no recorded value" in card.body


def test_run_card_labels_unknown_run_unmeasured() -> None:
    context = _context(None)
    citation = RunCitation(run_id="run-9")

    card = copilot_service._run_card(citation, context)

    assert card.title == "Unmeasured run"
