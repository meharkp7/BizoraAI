"""Application service for the experiment run lifecycle."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.run import (
    ExperimentRun,
    RunState,
    is_valid_transition,
)
from bizora.core.errors import BizoraError, ErrorCode, ExperimentStateError
from bizora.db.repository import (
    compare_and_set_run_state,
    experiment_run_from_record,
    get_experiment_run,
    get_graph_revision,
    save_experiment_run,
)


class ExperimentRunService:
    """Create, retrieve, and transition experiment runs transactionally."""

    @staticmethod
    def _current_time(now: datetime | None) -> datetime:
        """Return the supplied clock value or the current UTC time."""
        timestamp = now if now is not None else datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise BizoraError(
                ErrorCode.INVALID_REQUEST,
                "Run timestamps must be timezone-aware.",
            )
        return timestamp

    @staticmethod
    def create_run(
        session: Session,
        config: ExperimentConfig,
        *,
        run_id: str,
        now: datetime | None = None,
    ) -> ExperimentRun:
        """Validate the graph revision and persist a pending run."""
        timestamp = ExperimentRunService._current_time(now)

        try:
            revision = get_graph_revision(
                session,
                project_id=config.project_id,
                graph_id=config.graph_id,
                version=config.graph_version,
            )
            if revision is None:
                raise BizoraError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    "The referenced graph revision does not exist.",
                    details={
                        "project_id": config.project_id,
                        "graph_id": config.graph_id,
                        "version": config.graph_version,
                    },
                )

            run = ExperimentRun(
                run_id=run_id,
                config=config,
                state=RunState.PENDING,
                created_at=timestamp,
            )
            record = save_experiment_run(session, run)
            session.commit()
            return experiment_run_from_record(record)
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def get_run(session: Session, run_id: str) -> ExperimentRun:
        """Return one run or raise when it does not exist."""
        record = get_experiment_run(session, run_id)
        if record is None:
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "The experiment run does not exist.",
                details={"run_id": run_id},
            )
        return experiment_run_from_record(record)

    @staticmethod
    def transition_run(
        session: Session,
        run_id: str,
        *,
        to_state: RunState,
        now: datetime | None = None,
        error: str | None = None,
    ) -> ExperimentRun:
        """Move a run to a new state using an atomic compare-and-set."""
        timestamp = ExperimentRunService._current_time(now)

        try:
            current = get_experiment_run(session, run_id)
            if current is None:
                raise BizoraError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    "The experiment run does not exist.",
                    details={"run_id": run_id},
                )

            from_state = RunState(current.state)
            if not is_valid_transition(from_state, to_state):
                raise ExperimentStateError(
                    f"Cannot transition run '{run_id}' from "
                    f"'{from_state.value}' to '{to_state.value}'.",
                    details={
                        "run_id": run_id,
                        "from_state": from_state.value,
                        "to_state": to_state.value,
                    },
                )

            if error is not None and to_state not in (
                RunState.FAILED,
                RunState.CANCELLED,
            ):
                raise ExperimentStateError(
                    "Only failed or cancelled runs may carry an error message.",
                    details={"run_id": run_id, "to_state": to_state.value},
                )

            updated = compare_and_set_run_state(
                session,
                run_id=run_id,
                expected_state=from_state,
                new_state=to_state,
                now=timestamp,
                error=error,
            )
            if updated is None:
                raise BizoraError(
                    ErrorCode.RESOURCE_CONFLICT,
                    "The experiment run was modified concurrently; "
                    "reload it and retry the transition.",
                    details={"run_id": run_id},
                )

            session.commit()
            return experiment_run_from_record(updated)
        except Exception:
            session.rollback()
            raise
