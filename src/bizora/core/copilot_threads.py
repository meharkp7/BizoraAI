"""Persistence for copilot conversation threads.

Threads belong to one project graph and outlive its revisions: asking with a
``thread_id`` records the user message plus the final answer, so the panel can
list, resume, and re-render earlier conversations.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from bizora.contracts.components import (
    CopilotResponse,
    CopilotThread,
    CopilotThreadSummary,
    CopilotTurn,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db import repository
from bizora.db.models import CopilotThreadRecord

DEFAULT_THREAD_TITLE = "New conversation"
_TITLE_PREVIEW_LENGTH = 80


def _ensure_aware(value: datetime) -> datetime:
    """Return a timezone-aware timestamp, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _preview_title(message: str) -> str:
    """Derive a one-line thread title from the first user message."""
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    if len(first_line) > _TITLE_PREVIEW_LENGTH:
        return first_line[: _TITLE_PREVIEW_LENGTH - 1].rstrip() + "…"
    return first_line or DEFAULT_THREAD_TITLE


class CopilotThreadService:
    """Create, list, read, and append to copilot threads."""

    @staticmethod
    def _current_time(now: datetime | None) -> datetime:
        return now if now is not None else datetime.now(UTC)

    @classmethod
    def create_thread(
        cls,
        session: Session,
        *,
        project_id: str,
        graph_id: str,
        title: str | None,
        now: datetime | None = None,
    ) -> CopilotThreadSummary:
        """Persist one empty thread and return its summary."""
        timestamp = cls._current_time(now)
        record = repository.save_copilot_thread(
            session,
            thread_id=uuid.uuid4().hex,
            project_id=project_id,
            graph_id=graph_id,
            title=title.strip() if title and title.strip() else DEFAULT_THREAD_TITLE,
            now=timestamp,
        )
        session.commit()
        return CopilotThreadSummary(
            thread_id=record.thread_id,
            title=record.title,
            turn_count=0,
            updated_at=_ensure_aware(record.updated_at),
        )

    @staticmethod
    def list_threads(
        session: Session, *, project_id: str, graph_id: str
    ) -> list[CopilotThreadSummary]:
        """List one graph's threads, most recently active first."""
        records = repository.list_copilot_threads(
            session, project_id=project_id, graph_id=graph_id
        )
        counts = repository.count_copilot_turns(
            session, thread_ids=[record.thread_id for record in records]
        )
        return [
            CopilotThreadSummary(
                thread_id=record.thread_id,
                title=record.title,
                turn_count=counts.get(record.thread_id, 0),
                updated_at=_ensure_aware(record.updated_at),
            )
            for record in records
        ]

    @staticmethod
    def _thread_or_raise(
        session: Session, *, project_id: str, graph_id: str, thread_id: str
    ) -> CopilotThreadRecord:
        """Load one thread of this graph or raise the not-found error."""
        record = repository.get_copilot_thread(session, thread_id=thread_id)
        if (
            record is None
            or record.project_id != project_id
            or record.graph_id != graph_id
        ):
            raise BizoraError(
                ErrorCode.RESOURCE_NOT_FOUND,
                "The copilot thread was not found.",
                details={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "thread_id": thread_id,
                },
            )
        return record

    @classmethod
    def require_thread(
        cls, session: Session, *, project_id: str, graph_id: str, thread_id: str
    ) -> None:
        """Fail with not-found unless the thread belongs to this graph."""
        cls._thread_or_raise(
            session, project_id=project_id, graph_id=graph_id, thread_id=thread_id
        )

    @classmethod
    def get_thread(
        cls, session: Session, *, project_id: str, graph_id: str, thread_id: str
    ) -> CopilotThread:
        """Load one thread with its turns, oldest first."""
        record = cls._thread_or_raise(
            session, project_id=project_id, graph_id=graph_id, thread_id=thread_id
        )
        turns = repository.list_copilot_turns(session, thread_id=thread_id)
        return CopilotThread(
            thread_id=record.thread_id,
            title=record.title,
            turns=tuple(
                CopilotTurn(
                    seq=turn.seq,
                    role="assistant" if turn.role == "assistant" else "user",
                    message=turn.message,
                    response=(
                        CopilotResponse.model_validate(turn.response_payload)
                        if turn.response_payload is not None
                        else None
                    ),
                )
                for turn in turns
            ),
        )

    @classmethod
    def record_turn(
        cls,
        session: Session,
        *,
        project_id: str,
        graph_id: str,
        thread_id: str,
        message: str,
        response: CopilotResponse,
        now: datetime | None = None,
    ) -> None:
        """Append one user message plus its answer to a thread.

        The first recorded turn also names an untitled thread from the
        user's own message.
        """
        record = cls._thread_or_raise(
            session, project_id=project_id, graph_id=graph_id, thread_id=thread_id
        )
        timestamp = cls._current_time(now)
        existing = repository.list_copilot_turns(session, thread_id=thread_id)
        start = len(existing)
        repository.save_copilot_turn(
            session,
            thread_id=thread_id,
            seq=start,
            role="user",
            message=message,
            response_payload=None,
            now=timestamp,
        )
        repository.save_copilot_turn(
            session,
            thread_id=thread_id,
            seq=start + 1,
            role="assistant",
            message=response.reply,
            response_payload=response.model_dump(mode="json"),
            now=timestamp,
        )
        if not existing and record.title == DEFAULT_THREAD_TITLE:
            record.title = _preview_title(message)
        record.updated_at = timestamp
        session.commit()
