"""Authentication, accounts, and project-ownership checks."""

from bizora.auth.dependencies import (
    configure_auth,
    get_current_principal,
    get_optional_principal,
    require_project_membership,
    reset_auth,
)
from bizora.auth.membership import (
    InMemoryMembershipStore,
    MembershipStore,
    SqlAlchemyMembershipStore,
)
from bizora.auth.models import PaperNoteRow, ProjectMemberRow, UserPaperRow, UserRow
from bizora.auth.passwords import hash_password, verify_password
from bizora.auth.tokens import (
    FakeStaticTokenStore,
    Hs256TokenVerifier,
    TokenAuthError,
    TokenVerifier,
    mint_hs256_token,
    verify_hs256_token,
)

__all__ = [
    "FakeStaticTokenStore",
    "Hs256TokenVerifier",
    "InMemoryMembershipStore",
    "MembershipStore",
    "PaperNoteRow",
    "ProjectMemberRow",
    "SqlAlchemyMembershipStore",
    "TokenAuthError",
    "TokenVerifier",
    "UserPaperRow",
    "UserRow",
    "configure_auth",
    "get_current_principal",
    "get_optional_principal",
    "hash_password",
    "mint_hs256_token",
    "require_project_membership",
    "reset_auth",
    "verify_hs256_token",
    "verify_password",
]
