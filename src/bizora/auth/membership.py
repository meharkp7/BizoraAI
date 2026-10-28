"""Project-membership storage backends."""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.auth.models import ProjectMemberRow
from bizora.contracts.auth import ProjectMembership, ProjectRole
from bizora.core.errors import BizoraError, ErrorCode


@runtime_checkable
class MembershipStore(Protocol):
    """Interface implemented by project-membership backends."""

    def get_role(self, project_id: str, user_id: str) -> ProjectRole | None:
        """Return a user's role in a project, or None when not a member."""
        ...


class InMemoryMembershipStore:
    """CLEARLY-MARKED TEST FAKE: memberships held in process memory."""

    def __init__(self) -> None:
        self._roles: dict[tuple[str, str], ProjectRole] = {}

    def add_member(self, membership: ProjectMembership) -> None:
        """Record one fake membership for a test."""
        self._roles[(membership.project_id, membership.user_id)] = membership.role

    def remove_member(self, project_id: str, user_id: str) -> None:
        """Remove one fake membership for a test."""
        self._roles.pop((project_id, user_id), None)

    def get_role(self, project_id: str, user_id: str) -> ProjectRole | None:
        """Return a fake role, or None when not a member."""
        return self._roles.get((project_id, user_id))


class SqlAlchemyMembershipStore:
    """Durable membership backend over the project_members table."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get_role(self, project_id: str, user_id: str) -> ProjectRole | None:
        """Return a user's persisted role, or None when not a member."""
        session = self._session_factory()
        try:
            row = session.scalar(
                select(ProjectMemberRow).where(
                    ProjectMemberRow.project_id == project_id,
                    ProjectMemberRow.user_id == user_id,
                )
            )
            return ProjectRole(row.role) if row is not None else None
        finally:
            session.close()

    def add_member(self, membership: ProjectMembership) -> None:
        """Persist one membership; re-adding the same pair conflicts."""
        session = self._session_factory()
        try:
            session.add(
                ProjectMemberRow(
                    project_id=membership.project_id,
                    user_id=membership.user_id,
                    role=membership.role.value,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise BizoraError(
                    ErrorCode.RESOURCE_CONFLICT,
                    "The project membership already exists.",
                    details={
                        "project_id": membership.project_id,
                        "user_id": membership.user_id,
                    },
                ) from exc
        finally:
            session.close()

    def remove_member(self, project_id: str, user_id: str) -> None:
        """Remove one persisted membership; missing rows are a no-op."""
        session = self._session_factory()
        try:
            row = session.scalar(
                select(ProjectMemberRow).where(
                    ProjectMemberRow.project_id == project_id,
                    ProjectMemberRow.user_id == user_id,
                )
            )
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()
