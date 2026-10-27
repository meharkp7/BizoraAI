"""Tests for worker lease claiming, heartbeats, and reaping."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bizora.contracts.execution import ExecutionErrorCode, StructuredError
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.run import ExperimentRun, RunState
from bizora.db.base import Base
from bizora.db.repository import (
    claim_experiment_run,
    get_experiment_run,
    heartbeat_experiment_run,
    list_claimable_runs,
    reap_expired_leases,
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
        "adapter_id": "bizora.deterministic-test",
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
        "max_gpu_count": 0,
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


def save_pending(
    db_session: Session,
    *,
    run_id: str = "run-1",
    created_at: datetime | None = None,
) -> None:
    """Persist a pending run."""
    save_experiment_run(db_session, make_run(run_id=run_id, created_at=created_at))
    db_session.commit()


def lease_error_value() -> str:
    """Return the canonical lease-expiry error value."""
    return StructuredError(
        code=ExecutionErrorCode.LEASE_EXPIRED,
        message="Worker lease expired before the run finished.",
    ).to_record_value()


def test_list_claimable_returns_pending_oldest_first(
    db_session: Session,
) -> None:
    save_pending(
        db_session, run_id="run-old", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    save_pending(
        db_session, run_id="run-new", created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )

    runs = list_claimable_runs(db_session)

    assert [record.run_id for record in runs] == ["run-old", "run-new"]


def test_list_claimable_excludes_running_runs(db_session: Session) -> None:
    save_pending(db_session, run_id="run-1")
    save_pending(db_session, run_id="run-2")
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    db_session.commit()

    runs = list_claimable_runs(db_session)

    assert [record.run_id for record in runs] == ["run-2"]


def test_list_claimable_respects_limit(db_session: Session) -> None:
    save_pending(db_session, run_id="run-1")
    save_pending(db_session, run_id="run-2")

    runs = list_claimable_runs(db_session, limit=1)

    assert [record.run_id for record in runs] == ["run-1"]


def test_list_claimable_rejects_non_positive_limit(
    db_session: Session,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        list_claimable_runs(db_session, limit=0)


def test_claim_sets_running_state_worker_and_lease(
    db_session: Session,
) -> None:
    save_pending(db_session)
    now = datetime(2026, 1, 3, tzinfo=UTC)

    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=now,
        lease_ttl_seconds=300,
    )

    assert claimed is not None
    assert claimed.state == RunState.RUNNING.value
    assert claimed.worker_id == "worker-a"
    assert claimed.started_at is not None
    assert claimed.lease_expires_at is not None
    assert claimed.lease_expires_at - claimed.started_at == timedelta(seconds=300)


def test_second_claim_on_running_run_fails(db_session: Session) -> None:
    save_pending(db_session)
    now = datetime(2026, 1, 3, tzinfo=UTC)
    first = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=now,
        lease_ttl_seconds=300,
    )
    assert first is not None
    db_session.commit()

    second = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-b",
        now=now,
        lease_ttl_seconds=300,
    )

    assert second is None
    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.worker_id == "worker-a"


def test_claim_rejects_non_positive_ttl(db_session: Session) -> None:
    save_pending(db_session)

    with pytest.raises(ValueError, match="positive integer"):
        claim_experiment_run(
            db_session,
            run_id="run-1",
            worker_id="worker-a",
            now=datetime(2026, 1, 3, tzinfo=UTC),
            lease_ttl_seconds=0,
        )


def test_heartbeat_rejects_non_positive_ttl(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None

    with pytest.raises(ValueError, match="positive integer"):
        heartbeat_experiment_run(
            db_session,
            run_id="run-1",
            worker_id="worker-a",
            now=datetime(2026, 1, 3, 0, 4, tzinfo=UTC),
            lease_ttl_seconds=-10,
        )


def test_claim_on_missing_run_returns_none(db_session: Session) -> None:
    claimed = claim_experiment_run(
        db_session,
        run_id="missing-run",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )

    assert claimed is None


def test_heartbeat_extends_lease(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    assert claimed.lease_expires_at is not None
    previous_lease = claimed.lease_expires_at

    renewed = heartbeat_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, 0, 4, tzinfo=UTC),
        lease_ttl_seconds=300,
    )

    assert renewed is not None
    assert renewed.lease_expires_at is not None
    assert renewed.lease_expires_at > previous_lease


def test_heartbeat_rejects_other_worker(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    assert claimed.lease_expires_at is not None
    previous_lease = claimed.lease_expires_at

    renewed = heartbeat_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-b",
        now=datetime(2026, 1, 3, 0, 4, tzinfo=UTC),
        lease_ttl_seconds=300,
    )

    assert renewed is None
    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.lease_expires_at == previous_lease


def test_heartbeat_on_missing_run_returns_none(db_session: Session) -> None:
    renewed = heartbeat_experiment_run(
        db_session,
        run_id="missing-run",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )

    assert renewed is None


def test_reap_fails_expired_lease(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    db_session.commit()
    error = lease_error_value()

    reaped = reap_expired_leases(
        db_session,
        now=datetime(2026, 1, 3, 0, 6, tzinfo=UTC),
        error=error,
    )
    db_session.commit()

    assert reaped == 1
    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.state == RunState.FAILED.value
    assert current.error == error
    assert current.finished_at is not None


def test_reap_ignores_unexpired_lease(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    db_session.commit()

    reaped = reap_expired_leases(
        db_session,
        now=datetime(2026, 1, 3, 0, 4, tzinfo=UTC),
        error=lease_error_value(),
    )

    assert reaped == 0
    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.state == RunState.RUNNING.value


def test_reap_ignores_runs_without_lease(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    # Simulate an operator-managed run with no worker lease.
    claimed.worker_id = None
    claimed.lease_expires_at = None
    db_session.commit()

    reaped = reap_expired_leases(
        db_session,
        now=datetime(2026, 2, 1, tzinfo=UTC),
        error=lease_error_value(),
    )

    assert reaped == 0
    current = get_experiment_run(db_session, "run-1")
    assert current is not None
    assert current.state == RunState.RUNNING.value


def test_reap_fails_all_expired_leases(db_session: Session) -> None:
    save_pending(db_session, run_id="run-1")
    save_pending(db_session, run_id="run-2")
    now = datetime(2026, 1, 3, tzinfo=UTC)
    for run_id in ("run-1", "run-2"):
        claimed = claim_experiment_run(
            db_session,
            run_id=run_id,
            worker_id="worker-a",
            now=now,
            lease_ttl_seconds=300,
        )
        assert claimed is not None
    db_session.commit()

    reaped = reap_expired_leases(
        db_session,
        now=now + timedelta(hours=1),
        error=lease_error_value(),
    )
    db_session.commit()

    assert reaped == 2
    for run_id in ("run-1", "run-2"):
        current = get_experiment_run(db_session, run_id)
        assert current is not None
        assert current.state == RunState.FAILED.value


def test_heartbeat_after_reap_returns_none(db_session: Session) -> None:
    save_pending(db_session)
    claimed = claim_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, tzinfo=UTC),
        lease_ttl_seconds=300,
    )
    assert claimed is not None
    db_session.commit()
    reaped = reap_expired_leases(
        db_session,
        now=datetime(2026, 1, 3, 0, 6, tzinfo=UTC),
        error=lease_error_value(),
    )
    assert reaped == 1

    renewed = heartbeat_experiment_run(
        db_session,
        run_id="run-1",
        worker_id="worker-a",
        now=datetime(2026, 1, 3, 0, 7, tzinfo=UTC),
        lease_ttl_seconds=300,
    )

    assert renewed is None
