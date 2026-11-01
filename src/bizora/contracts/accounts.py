"""Account, paper-library, and note contracts for JWT login.

Email/password login returns HS256 Bearer [REDACTED] usable from curl as
well as the web login; no browser-only flows.
"""

import re

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    """Lowercase and sanity-check an email address (no new dependencies)."""
    cleaned = value.strip().lower()
    if not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("Enter a valid email address.")
    return cleaned


class RegisterRequest(BaseModel):
    """Create one login account."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=128)

    @field_validator("email")
    @classmethod
    def _clean_email(cls, value: str) -> str:
        return _normalize_email(value)


class LoginRequest(BaseModel):
    """Exchange an email and password for a token."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _clean_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserSummary(BaseModel):
    """One account, safe to return to its owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(max_length=128)
    created_at: AwareDatetime


class AuthResponse(BaseModel):
    """A login: the account plus its Bearer [REDACTED]"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user: UserSummary
    token: str = Field(min_length=1)
    expires_at: AwareDatetime


class SavePaperRequest(BaseModel):
    """Attach one ingested paper to the caller's library."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)


class PaperSummary(BaseModel):
    """One library entry with the ids that route it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    created_at: AwareDatetime


class NoteCreateRequest(BaseModel):
    """Write one note on a paper."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)


class NoteSummary(BaseModel):
    """One stored note."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    paper_id: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=10000)
    created_at: AwareDatetime
    updated_at: AwareDatetime
