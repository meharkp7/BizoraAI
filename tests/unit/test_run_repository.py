"""Tests for experiment run persistence and atomic transitions."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.run import ExperimentRun, RunState
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base
from bizora.db.repository import (
    compare_and_set_run_state,
    experiment_run_from_record,
    get_experiment_run,
    save_experiment_run,
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
        "adapter_id": "hf-vit-classification",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {
            "train": 0.8,
            "validation": 0.1,
            "test": 0.1,
        },
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 1,
    }


def make_run(
    *,
    run_id: str = "run-1",
    created_at: datetime | None = None,
) -> ExperimentRun:
    """Build a minimal pending run."""
    return ExperimentRun(
        run_id=run_id,
        config=ExperimentConfig.model_validate(valid_experiment_data()),
        state=RunState.PENDING,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_save_and_retrieve_run_round_trips_config(
    db_session: Session,
) -> None:
    run = make_run()

    record = save_experiment_run(db_session, run)
    db_session.commit()

    assert record.id is not None
    assert record.run_id == "run-1"
    assert record.experiment_id == "exp-1"
    assert record.project_id == "project-1"
    assert record.graph_id == "graph-1"
    assert record.graph_version == 1
    assert record.state == RunState.PENDING.value

    loaded = get_experiment_run(db_session, "run-1")
    assert loaded is not None
    restored = experiment_run_from_record(loaded)
    assert restored == run
    assert restored.created_at.tzinfo is not None


def test_duplicate_run_id_is_rejected(db_session: Session) -> None:
    save_experiment_run(db_session, make_run())
    db_session.commit()

    with pytest.raises(BizoraError) as exc_info:
        save_experiment_run(db_session, make_run())

    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT
    assert exc_info.value.details == {"run_id": "run-1"}


def test_missing_run_returns_none(db_session: Session) -> None:
    assert get_experiment_run(db_session, "missing-run") is None


def test_atomic_transition_stamps_started_at(db_session: Session) -> None:
    save_experiment_run(db_session, make_run())
    db_session.commit()
    now = datetime(2026, 1, 2, tzinfo=UTC)

    updated = compare_and_set_run_state(
        db_session,
        run_id="run-1",
        expected_state=RunState.PENDING,
        new_state=RunState.RUNNING,
        now=now,
        error=None,
    )
    db_session.commit()

    assert updated is not None
    assert updated.state == RunState.RUNNING.value
    restored = experiment_run_from_record(updated)
    assert restored.state == RunState.RUNNING
    assert restored.started_at == now
    assert restored.finished_at is None


def test_atomic_transition_with_wrong_expected_state_leaves_row(
    db_session: Session,
) -> None:
    save_experiment_run(db_session, make_run())
    db_session.commit()

    updated = compare_and_set_run_state(
        db_session,
        run_id="run-1",
        expected_state=RunState.RUNNING,
        new_state=RunState.SUCCEEDED,
        now=datetime(2026, 1, 3, tzinfo=UTC),
        error=None,
    )

    assert updated is None

    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.state == RunState.PENDING.value
    assert current.finished_at is None


def test_atomic_transition_on_missing_run_returns_none(
    db_session: Session,
) -> None:
    updated = compare_and_set_run_state(
        db_session,
        run_id="missing-run",
        expected_state=RunState.PENDING,
        new_state=RunState.RUNNING,
        now=datetime(2026, 1, 2, tzinfo=UTC),
        error=None,
    )

    assert updated is None


def test_atomic_transition_to_terminal_stamps_finished_at(
    db_session: Session,
) -> None:
    save_experiment_run(db_session, make_run())
    db_session.commit()
    started = datetime(2026, 1, 2, tzinfo=UTC)
    finished = datetime(2026, 1, 3, tzinfo=UTC)

    running = compare_and_set_run_state(
        db_session,
        run_id="run-1",
        expected_state=RunState.PENDING,
        new_state=RunState.RUNNING,
        now=started,
        error=None,
    )
    assert running is not None

    succeeded = compare_and_set_run_state(
        db_session,
        run_id="run-1",
        expected_state=RunState.RUNNING,
        new_state=RunState.SUCCEEDED,
        now=finished,
        error=None,
    )
    db_session.commit()

    assert succeeded is not None
    restored = experiment_run_from_record(succeeded)
    assert restored.state == RunState.SUCCEEDED
    assert restored.started_at == started
    assert restored.finished_at == finished


def test_atomic_transition_returns_fresh_record_without_expiry() -> None:
    """Guard against stale identity-map reads under production session config."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db_session:
            save_experiment_run(db_session, make_run())
            db_session.commit()

            preloaded = get_experiment_run(db_session, "run-1")
            assert preloaded is not None
            assert preloaded.state == RunState.PENDING.value

            updated = compare_and_set_run_state(
                db_session,
                run_id="run-1",
                expected_state=RunState.PENDING,
                new_state=RunState.RUNNING,
                now=datetime(2026, 1, 2, tzinfo=UTC),
                error=None,
            )

            assert updated is not None
            assert updated.state == RunState.RUNNING.value
            assert updated.started_at is not None
    finally:
        engine.dispose()


def test_cancel_from_pending_keeps_started_at_empty(
    db_session: Session,
) -> None:
    save_experiment_run(db_session, make_run())
    db_session.commit()
    finished = datetime(2026, 1, 3, tzinfo=UTC)

    cancelled = compare_and_set_run_state(
        db_session,
        run_id="run-1",
        expected_state=RunState.PENDING,
        new_state=RunState.CANCELLED,
        now=finished,
        error="cancelled by request",
    )
    db_session.commit()

    assert cancelled is not None
    restored = experiment_run_from_record(cancelled)
    assert restored.state == RunState.CANCELLED
    assert restored.started_at is None
    assert restored.finished_at == finished
    assert restored.error == "cancelled by request"
