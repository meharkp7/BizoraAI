"""Authentication and project-ownership contracts.

Principals are resolved from bearer tokens; project access is checked
against explicit membership rows. Endpoint wiring is a later step: this
module only defines the reusable contracts and dependency callables.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProjectRole(StrEnum):
    """Membership level within one project, weakest to strongest."""

    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


ROLE_RANK: dict[ProjectRole, int] = {
    ProjectRole.VIEWER: 1,
    ProjectRole.EDITOR: 2,
    ProjectRole.OWNER: 3,
}


def role_satisfies(actual: ProjectRole, required: ProjectRole) -> bool:
    """Return whether an actual role meets a minimum required role."""
    return ROLE_RANK[actual] >= ROLE_RANK[required]


class Principal(BaseModel):
    """An authenticated caller resolved from a bearer token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1, max_length=128)
    expires_at: AwareDatetime | None = None
    token_id: str | None = Field(default=None, min_length=1, max_length=128)


class ProjectMembership(BaseModel):
    """One user's explicit membership in one project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    role: ProjectRole
