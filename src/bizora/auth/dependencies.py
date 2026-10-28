"""Reusable FastAPI dependencies for auth and project ownership.

NOT wired into any endpoint: import these in route modules when the
API is ready to require authentication. Auth backends are configured
once at application startup via :func:`configure_auth`.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bizora.auth.membership import MembershipStore
from bizora.auth.tokens import TokenAuthError, TokenVerifier
from bizora.contracts.auth import Principal, ProjectRole

_bearer_scheme = HTTPBearer(auto_error=False)
BEARER_CREDENTIALS_DEPENDENCY = Depends(_bearer_scheme)

_configured_verifier: TokenVerifier | None = None
_configured_store: MembershipStore | None = None


def configure_auth(verifier: TokenVerifier, store: MembershipStore) -> None:
    """Set the process-wide token verifier and membership store."""
    global _configured_verifier, _configured_store
    _configured_verifier = verifier
    _configured_store = store


def reset_auth() -> None:
    """Clear auth configuration (tests only)."""
    global _configured_verifier, _configured_store
    _configured_verifier = None
    _configured_store = None


def _require_verifier() -> TokenVerifier:
    """Return the configured verifier or fail closed."""
    if _configured_verifier is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured.",
        )
    return _configured_verifier


def _require_store() -> MembershipStore:
    """Return the configured membership store or fail closed."""
    if _configured_store is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Project membership storage is not configured.",
        )
    return _configured_store


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = BEARER_CREDENTIALS_DEPENDENCY,
) -> Principal:
    """Resolve the bearer token to a principal; 401 without one."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return _require_verifier().verify(credentials.credentials)
    except TokenAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


PRINCIPAL_DEPENDENCY = Depends(get_current_principal)


def require_project_membership(
    project_id: str,
    *allowed_roles: ProjectRole,
) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Build a dependency requiring membership in one project.

    With no roles, any membership grants access; with roles, the
    caller's role must be one of them. Returns the principal so routes
    can audit who acted.
    """
    allowed = frozenset(allowed_roles)

    async def check_membership(
        principal: Principal = PRINCIPAL_DEPENDENCY,
    ) -> Principal:
        role = _require_store().get_role(project_id, principal.user_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this project.",
            )
        if allowed and role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action requires a different project role.",
            )
        return principal

    return check_membership
