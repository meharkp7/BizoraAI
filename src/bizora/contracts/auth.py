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


class InviteStatus(StrEnum):
    """Lifecycle of a project invite, in transition order."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class InviteCreateRequest(BaseModel):
    """Ask the project to invite one email address at a role."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: ProjectRole = ProjectRole.VIEWER


class InviteSummary(BaseModel):
    """Public view of one invite. The bearer token is never listed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    invite_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    role: ProjectRole
    status: InviteStatus
    created_by: str = Field(min_length=1, max_length=128)
    created_at: AwareDatetime
    expires_at: AwareDatetime


class InviteCreateResponse(BaseModel):
    """Creation response: the only time the bearer token is shown."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    invite: InviteSummary
    token: str = Field(min_length=1)


class InviteAcceptRequest(BaseModel):
    """Accept an invite by presenting its bearer [REDACTED]"""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=2048)
