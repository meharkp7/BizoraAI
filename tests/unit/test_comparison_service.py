"""Tests for the baseline comparison service."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.comparison import ComparisonVerdict
from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.run import ExperimentRun, MetricRecord, RunState
from bizora.core.comparison_service import ComparisonService
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base
from bizora.db.repository import (
    get_experiment_run,
    get_metric_record,
    save_experiment_run,
    save_metric_record,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def valid_experiment_data() -> dict[str, object]:
    """Return a valid experiment configuration payload."""
    return {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "bizora.deterministic-test",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 0,
    }


def make_config(**overrides: object) -> ExperimentConfig:
    """Build a config with overridden fields."""
    payload = valid_experiment_data()
    payload.update(overrides)
    return ExperimentConfig.model_validate(payload)


def seed_run(
    db_session: Session,
    *,
    run_id: str,
    config: ExperimentConfig,
    state: RunState = RunState.SUCCEEDED,
) -> None:
    """Persist one run in the given terminal-capable state."""
    started = datetime(2026, 1, 2, tzinfo=UTC)
    finished = datetime(2026, 1, 3, tzinfo=UTC)
    terminal = state in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED)
    run = ExperimentRun(
        run_id=run_id,
        config=config,
        state=state,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        started_at=started if state != RunState.PENDING else None,
        finished_at=finished if terminal else None,
    )
    save_experiment_run(db_session, run)
    db_session.commit()


def seed_metric(
    db_session: Session,
    *,
    run_id: str,
    metric_id: str,
    name: str,
    value: float,
    result_kind: ResultKind = ResultKind.MEASURED,
) -> None:
    """Persist one metric record for a run."""
    save_metric_record(
        db_session,
        MetricRecord(
            metric_id=metric_id,
            run_id=run_id,
            name=name,
            value=value,
            result_kind=result_kind,
        ),
    )
    db_session.commit()


def seed_valid_pair(db_session: Session) -> None:
    """Persist a baseline and variant differing only by graph version."""
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline", graph_version=1),
    )
    seed_run(
        db_session,
        run_id="run-variant",
        config=make_config(experiment_id="exp-variant", graph_version=2),
    )
    seed_metric(
        db_session,
        run_id="run-baseline",
        metric_id="m-accuracy",
        name="accuracy",
        value=0.8,
    )
    seed_metric(
        db_session,
        run_id="run-variant",
        metric_id="m-accuracy",
        name="accuracy",
        value=0.9,
    )


def test_valid_comparison_reports_exact_changes(db_session: Session) -> None:
    seed_valid_pair(db_session)

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.VALID
    assert comparison.reasons == ()
    assert comparison.graph.baseline_graph_version == 1
    assert comparison.graph.variant_graph_version == 2
    assert len(comparison.metrics) == 1
    metric = comparison.metrics[0]
    assert metric.name == "accuracy"
    assert metric.baseline_value == 0.8
    assert metric.variant_value == 0.9
    assert metric.absolute_change == pytest.approx(0.1)
    assert metric.relative_change == pytest.approx(0.125)
    assert comparison.config_differences == ()


def test_zero_baseline_leaves_relative_change_undefined(
    db_session: Session,
) -> None:
    seed_valid_pair(db_session)
    session = db_session
    row = get_metric_record(session, run_id="run-baseline", metric_id="m-accuracy")
    assert row is not None
    row.value = 0.0
    session.commit()

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.VALID
    metric = comparison.metrics[0]
    assert metric.relative_change is None
    assert metric.relative_undefined_reason == "Baseline value is zero."


def test_seed_difference_confounds_comparison(db_session: Session) -> None:
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline"),
    )
    seed_run(
        db_session,
        run_id="run-variant",
        config=make_config(experiment_id="exp-variant", seed=7, graph_version=2),
    )
    seed_metric(
        db_session, run_id="run-baseline", metric_id="m", name="accuracy", value=0.8
    )
    seed_metric(
        db_session, run_id="run-variant", metric_id="m", name="accuracy", value=0.9
    )

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.CONFOUNDED
    assert comparison.reasons == ("Configuration field 'seed' differs.",)
    assert len(comparison.metrics) == 1
    assert comparison.config_differences[0].field == "seed"
    assert comparison.config_differences[0].baseline == 42
    assert comparison.config_differences[0].variant == 7


def test_dataset_revision_difference_confounds(db_session: Session) -> None:
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline"),
    )
    seed_run(
        db_session,
        run_id="run-variant",
        config=make_config(
            experiment_id="exp-variant",
            dataset_revision="sha256:other",
            graph_version=2,
        ),
    )
    seed_metric(
        db_session, run_id="run-baseline", metric_id="m", name="accuracy", value=0.8
    )
    seed_metric(
        db_session, run_id="run-variant", metric_id="m", name="accuracy", value=0.9
    )

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.CONFOUNDED
    assert "dataset_revision" in comparison.reasons[0]


def test_different_datasets_invalidate_comparison(
    db_session: Session,
) -> None:
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline"),
    )
    seed_run(
        db_session,
        run_id="run-variant",
        config=make_config(
            experiment_id="exp-variant", dataset_id="other-dataset"
        ),
    )
    seed_metric(
        db_session, run_id="run-baseline", metric_id="m", name="accuracy", value=0.8
    )
    seed_metric(
        db_session, run_id="run-variant", metric_id="m", name="accuracy", value=0.9
    )

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.INVALID
    assert comparison.metrics == ()
    assert any("different datasets" in reason for reason in comparison.reasons)


def test_failed_run_invalidates_comparison(db_session: Session) -> None:
    seed_valid_pair(db_session)
    session = db_session
    record = get_experiment_run(session, "run-variant")
    assert record is not None
    record.state = RunState.FAILED.value
    session.commit()

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.INVALID
    assert comparison.metrics == ()
    assert comparison.reasons == ("Variant run is 'failed', not succeeded.",)


def test_no_shared_metrics_invalidates_comparison(
    db_session: Session,
) -> None:
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline"),
    )
    seed_run(
        db_session,
        run_id="run-variant",
        config=make_config(experiment_id="exp-variant", graph_version=2),
    )
    seed_metric(
        db_session, run_id="run-baseline", metric_id="m", name="accuracy", value=0.8
    )
    seed_metric(
        db_session, run_id="run-variant", metric_id="m", name="loss", value=0.2
    )

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.INVALID
    assert comparison.reasons == ("Runs share no measured metrics.",)
    assert sorted(
        (item.name, item.reason) for item in comparison.skipped_metrics
    ) == [
        ("accuracy", "Only reported by baseline run."),
        ("loss", "Only reported by variant run."),
    ]


def test_non_measured_metrics_are_skipped(db_session: Session) -> None:
    seed_valid_pair(db_session)
    seed_metric(
        db_session,
        run_id="run-baseline",
        metric_id="m-est",
        name="estimate",
        value=0.5,
        result_kind=ResultKind.ESTIMATED,
    )
    seed_metric(
        db_session,
        run_id="run-variant",
        metric_id="m-est",
        name="estimate",
        value=0.6,
        result_kind=ResultKind.MEASURED,
    )

    comparison = ComparisonService.compare_runs(
        db_session,
        baseline_run_id="run-baseline",
        variant_run_id="run-variant",
    )

    assert comparison.verdict == ComparisonVerdict.VALID
    assert [metric.name for metric in comparison.metrics] == ["accuracy"]
    assert len(comparison.skipped_metrics) == 1
    assert comparison.skipped_metrics[0].name == "estimate"
    assert comparison.skipped_metrics[0].reason == "Not measured in both runs."


def test_missing_run_raises_not_found(db_session: Session) -> None:
    seed_run(
        db_session,
        run_id="run-baseline",
        config=make_config(experiment_id="exp-baseline"),
    )

    with pytest.raises(BizoraError) as exc_info:
        ComparisonService.compare_runs(
            db_session,
            baseline_run_id="run-baseline",
            variant_run_id="missing-run",
        )

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
