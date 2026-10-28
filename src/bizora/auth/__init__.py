"""Authentication and project-ownership checks.

Reusable FastAPI dependencies; intentionally NOT wired into any
endpoint yet. Endpoint wiring is a follow-up that touches api.py.
"""

from bizora.auth.dependencies import (
    configure_auth,
    get_current_principal,
    require_project_membership,
    reset_auth,
)
from bizora.auth.membership import (
    InMemoryMembershipStore,
    MembershipStore,
    SqlAlchemyMembershipStore,
)
from bizora.auth.models import ProjectMemberRow
from bizora.auth.tokens import (
    FakeStaticTokenStore,
    Hs256TokenVerifier,
    TokenAuthError,
    TokenVerifier,
    verify_hs256_token,
)

__all__ = [
    "FakeStaticTokenStore",
    "Hs256TokenVerifier",
    "InMemoryMembershipStore",
    "MembershipStore",
    "ProjectMemberRow",
    "SqlAlchemyMembershipStore",
    "TokenAuthError",
    "TokenVerifier",
    "configure_auth",
    "get_current_principal",
    "require_project_membership",
    "reset_auth",
    "verify_hs256_token",
]
