"""User accounts, personal paper libraries, and per-paper notes.

Terminal-first JWT auth: register and login return HS256 Bearer [REDACTED]
over plain JSON, so curl works as well as the web login::

    curl -X POST localhost:8000/api/v1/auth/register \\
      -H 'Content-Type: application/json' \\
      -d '{"email":"me@example.com","password":"correct-horse-9","name":"Me"}'
    curl localhost:8000/api/v1/auth/me \\
      -H "Authorization: Bearer <token>"
"""

import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bizora.auth.dependencies import (
    OPTIONAL_PRINCIPAL_DEPENDENCY,
    PRINCIPAL_DEPENDENCY,
    get_membership_store,
)
from bizora.auth.membership import MembershipStore
from bizora.auth.models import PaperNoteRow, UserPaperRow, UserRow
from bizora.auth.passwords import hash_password, verify_password
from bizora.auth.tokens import Hs256TokenVerifier, mint_hs256_token
from bizora.contracts.accounts import (
    AuthResponse,
    LoginRequest,
    NoteCreateRequest,
    NoteSummary,
    PaperSummary,
    RegisterRequest,
    SavePaperRequest,
    UserSummary,
)
from bizora.contracts.auth import (
    InviteAcceptRequest,
    InviteCreateRequest,
    InviteCreateResponse,
    InviteStatus,
    InviteSummary,
    Principal,
    ProjectRole,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.invites import InviteService
from bizora.core.papers import is_valid_source_id
from bizora.db.models import ProjectInvite
from bizora.db.session import get_db_session

router = APIRouter()

DB_SESSION_DEPENDENCY = Depends(get_db_session)
MEMBERSHIP_STORE_DEPENDENCY = Depends(get_membership_store)


def _auth_secret() -> str:
    """Return the signing secret or fail with a configuration error."""
    secret = os.environ.get(Hs256TokenVerifier.ENV_VAR, "")
    if not secret:
        raise BizoraError(
            ErrorCode.INVALID_CONFIGURATION,
            "Token signing is not configured.",
        )
    return secret


def _aware(value: datetime) -> datetime:
    """Return a timezone-aware timestamp, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _user_summary(row: UserRow) -> UserSummary:
    """Project one user row onto its public summary."""
    return UserSummary(
        user_id=row.id,
        email=row.email,
        name=row.name,
        created_at=_aware(row.created_at),
    )


def _note_summary(row: PaperNoteRow) -> NoteSummary:
    """Project one note row onto its public summary."""
    return NoteSummary(
        id=row.id,
        paper_id=row.paper_id,
        body=row.body,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _paper_summary(row: UserPaperRow) -> PaperSummary:
    """Project one library row onto its public summary."""
    return PaperSummary(
        project_id=row.project_id,
        graph_id=row.graph_id,
        source_id=row.source_id,
        title=row.title,
        created_at=_aware(row.created_at),
    )


def _login_response(row: UserRow) -> AuthResponse:
    """Mint a token for one user row."""
    token, expires_at = mint_hs256_token(row.id, _auth_secret())
    return AuthResponse(user=_user_summary(row), token=token, expires_at=expires_at)


def _owned_note(session: Session, note_id: int, user_id: str) -> PaperNoteRow:
    """Fetch one note owned by one user; anything else is 404."""
    row = session.scalar(
        select(PaperNoteRow).where(
            PaperNoteRow.id == note_id,
            PaperNoteRow.user_id == user_id,
        )
    )
    if row is None:
        raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Note not found.")
    return row


@router.post(
    "/api/v1/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register_account(
    request: RegisterRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> AuthResponse:
    """Create one login account and return its first token."""
    existing = session.scalar(select(UserRow).where(UserRow.email == request.email))
    if existing is not None:
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "An account with this email already exists.",
        )
    row = UserRow(
        id=uuid.uuid4().hex,
        email=request.email,
        name=request.name.strip() or request.email.split("@")[0],
        password_hash=hash_password(request.password),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise BizoraError(
            ErrorCode.RESOURCE_CONFLICT,
            "An account with this email already exists.",
        ) from exc
    session.refresh(row)
    return _login_response(row)


@router.post("/api/v1/auth/login", response_model=AuthResponse, tags=["auth"])
def login_account(
    request: LoginRequest,
    session: Session = DB_SESSION_DEPENDENCY,
) -> AuthResponse:
    """Exchange an email and password for a token."""
    row = session.scalar(select(UserRow).where(UserRow.email == request.email))
    if row is None or not verify_password(request.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _login_response(row)


@router.get("/api/v1/auth/me", response_model=UserSummary, tags=["auth"])
def read_own_account(
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> UserSummary:
    """Return the caller's own account."""
    row = session.scalar(select(UserRow).where(UserRow.id == principal.user_id))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown user.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _user_summary(row)


@router.get(
    "/api/v1/users/me/papers",
    response_model=list[PaperSummary],
    tags=["papers"],
)
def list_own_papers(
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[PaperSummary]:
    """List the caller's paper library, newest first."""
    rows = session.scalars(
        select(UserPaperRow)
        .where(UserPaperRow.user_id == principal.user_id)
        .order_by(UserPaperRow.created_at.desc(), UserPaperRow.id.desc())
    )
    return [_paper_summary(row) for row in rows]


def record_user_paper(
    session: Session,
    user_id: str,
    *,
    project_id: str,
    graph_id: str,
    source_id: str,
    title: str,
) -> UserPaperRow:
    """Attach one paper to one library, refreshing it on re-save."""
    row = session.scalar(
        select(UserPaperRow).where(
            UserPaperRow.user_id == user_id,
            UserPaperRow.project_id == project_id,
        )
    )
    if row is None:
        row = UserPaperRow(
            user_id=user_id,
            project_id=project_id,
            graph_id=graph_id,
            source_id=source_id,
            title=title,
        )
        session.add(row)
    else:
        row.graph_id = graph_id
        row.source_id = source_id
        row.title = title
    session.commit()
    session.refresh(row)
    return row


@router.post("/api/v1/users/me/papers", response_model=PaperSummary, tags=["papers"])
def save_own_paper(
    request: SavePaperRequest,
    response: Response,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> PaperSummary:
    """Attach one ingested paper to the caller's library."""
    if not is_valid_source_id(request.source_id):
        raise BizoraError(
            ErrorCode.INVALID_REQUEST,
            "Source IDs may contain letters, digits, and . _ : - (max 128).",
            details={"source_id": request.source_id},
        )
    existed = (
        session.scalar(
            select(UserPaperRow.id).where(
                UserPaperRow.user_id == principal.user_id,
                UserPaperRow.project_id == request.project_id,
            )
        )
        is not None
    )
    row = record_user_paper(
        session,
        principal.user_id,
        project_id=request.project_id,
        graph_id=request.graph_id,
        source_id=request.source_id,
        title=request.title,
    )
    response.status_code = (
        status.HTTP_200_OK if existed else status.HTTP_201_CREATED
    )
    return _paper_summary(row)


def _checked_paper_id(paper_id: str) -> str:
    """Accept one notes paper id or 404 like the diagrams endpoint."""
    if not is_valid_source_id(paper_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found.",
        )
    return paper_id


@router.get(
    "/api/v1/papers/{paper_id}/notes",
    response_model=list[NoteSummary],
    tags=["notes"],
)
def list_paper_notes(
    paper_id: str,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> list[NoteSummary]:
    """List the caller's notes on one paper, oldest first."""
    _checked_paper_id(paper_id)
    rows = session.scalars(
        select(PaperNoteRow)
        .where(
            PaperNoteRow.user_id == principal.user_id,
            PaperNoteRow.paper_id == paper_id,
        )
        .order_by(PaperNoteRow.id.asc())
    )
    return [_note_summary(row) for row in rows]


@router.post(
    "/api/v1/papers/{paper_id}/notes",
    response_model=NoteSummary,
    status_code=status.HTTP_201_CREATED,
    tags=["notes"],
)
def create_paper_note(
    paper_id: str,
    request: NoteCreateRequest,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> NoteSummary:
    """Write one note on a paper."""
    _checked_paper_id(paper_id)
    body = request.body.strip()
    if not body:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Note body must be non-empty.")
    row = PaperNoteRow(user_id=principal.user_id, paper_id=paper_id, body=body)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _note_summary(row)


@router.put("/api/v1/papers/{paper_id}/notes/{note_id}", response_model=NoteSummary, tags=["notes"])
def update_paper_note(
    paper_id: str,
    note_id: int,
    request: NoteCreateRequest,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> NoteSummary:
    """Rewrite one of the caller's notes."""
    _checked_paper_id(paper_id)
    body = request.body.strip()
    if not body:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Note body must be non-empty.")
    row = _owned_note(session, note_id, principal.user_id)
    if row.paper_id != paper_id:
        raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Note not found.")
    row.body = body
    session.commit()
    session.refresh(row)
    return _note_summary(row)


@router.delete(
    "/api/v1/papers/{paper_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["notes"],
)
def delete_paper_note(
    paper_id: str,
    note_id: int,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
) -> None:
    """Delete one of the caller's notes."""
    _checked_paper_id(paper_id)
    row = _owned_note(session, note_id, principal.user_id)
    if row.paper_id != paper_id:
        raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Note not found.")
    session.delete(row)
    session.commit()


def _invite_summary(record: ProjectInvite) -> InviteSummary:
    """Project one invite row onto its public summary (never the token)."""
    return InviteSummary(
        invite_id=record.id,
        project_id=record.project_id,
        email=record.email,
        role=ProjectRole(record.role),
        status=InviteStatus(record.status),
        created_by=record.created_by,
        created_at=_aware(record.created_at),
        expires_at=_aware(record.expires_at),
    )


@router.post(
    "/api/v1/projects/{project_id}/invites",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["collab"],
)
def create_project_invite(
    project_id: str,
    request: InviteCreateRequest,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
    store: MembershipStore = MEMBERSHIP_STORE_DEPENDENCY,
) -> InviteCreateResponse:
    """Invite one email address to the project at a role.

    Any authenticated user may invite; the response carries the
    one-time bearer token for the invite link.
    """
    service = InviteService(session, store, secret=_auth_secret())
    record, token = service.create_invite(
        project_id=project_id,
        email=request.email,
        role=request.role,
        created_by=principal.user_id,
    )
    return InviteCreateResponse(invite=_invite_summary(record), token=token)


@router.get(
    "/api/v1/projects/{project_id}/invites",
    response_model=list[InviteSummary],
    tags=["collab"],
)
def list_project_invites(
    project_id: str,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
    store: MembershipStore = MEMBERSHIP_STORE_DEPENDENCY,
) -> list[InviteSummary]:
    """List the project's invites, newest first."""
    del principal
    service = InviteService(session, store, secret=_auth_secret())
    return [_invite_summary(record) for record in service.list_invites(project_id=project_id)]


@router.post(
    "/api/v1/projects/{project_id}/invites/{invite_id}/accept",
    response_model=InviteSummary,
    tags=["collab"],
)
def accept_project_invite(
    project_id: str,
    invite_id: str,
    request: InviteAcceptRequest,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
    store: MembershipStore = MEMBERSHIP_STORE_DEPENDENCY,
) -> InviteSummary:
    """Accept an invite, joining the project as the caller."""
    service = InviteService(session, store, secret=_auth_secret())
    record = service.accept_invite(
        project_id=project_id,
        invite_id=invite_id,
        token=request.token,
        user_id=principal.user_id,
    )
    return _invite_summary(record)


@router.delete(
    "/api/v1/projects/{project_id}/invites/{invite_id}",
    response_model=InviteSummary,
    tags=["collab"],
)
def revoke_project_invite(
    project_id: str,
    invite_id: str,
    principal: Principal = PRINCIPAL_DEPENDENCY,
    session: Session = DB_SESSION_DEPENDENCY,
    store: MembershipStore = MEMBERSHIP_STORE_DEPENDENCY,
) -> InviteSummary:
    """Revoke a pending invite."""
    del principal
    service = InviteService(session, store, secret=_auth_secret())
    record = service.revoke_invite(project_id=project_id, invite_id=invite_id)
    return _invite_summary(record)


# Re-exported so route modules share one optional-auth dependency.
__all__ = ["OPTIONAL_PRINCIPAL_DEPENDENCY", "record_user_paper", "router"]
