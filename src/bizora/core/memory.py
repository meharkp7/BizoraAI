"""Project memory: store, list, and forget copilot facts."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bizora.contracts.memory import MemoryFact
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db import repository
from bizora.db.models import MemoryRecord


def _fact_from_record(record: MemoryRecord) -> MemoryFact:
    """Convert one stored row into its contract."""
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return MemoryFact(
        id=record.id,
        project_id=record.project_id,
        fact=record.fact,
        created_by=record.created_by,
        created_at=created_at,
    )


class MemoryService:
    """Persist project memory facts with immediate commits."""

    @staticmethod
    def create_fact(
        session: Session,
        *,
        project_id: str,
        fact: str,
        created_by: str,
        now: datetime | None = None,
    ) -> MemoryFact:
        """Store one fact and return it."""
        record = repository.save_memory_fact(
            session,
            project_id=project_id,
            fact=fact.strip(),
            created_by=created_by,
            now=now if now is not None else datetime.now(UTC),
        )
        session.commit()
        return _fact_from_record(record)

    @staticmethod
    def list_facts(
        session: Session, *, project_id: str, limit: int = 50
    ) -> list[MemoryFact]:
        """List one project's facts, newest first."""
        return [
            _fact_from_record(record)
            for record in repository.list_memory_facts(
                session, project_id=project_id, limit=limit
            )
        ]

    @staticmethod
    def delete_fact(session: Session, *, project_id: str, fact_id: int) -> None:
        """Forget one fact or raise the not-found error."""
        if not repository.delete_memory_fact(
            session, project_id=project_id, fact_id=fact_id
        ):
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "The memory fact was not found.",
                details={"project_id": project_id, "fact_id": fact_id},
            )
        session.commit()
