"""Create project invite storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_project_invites"
down_revision: str | None = "0015_memory_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent project invite storage."""
    op.create_table(
        "project_invites",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("accepted_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_project_invite_token"),
    )
    op.create_index(
        "ix_project_invite_project",
        "project_invites",
        ["project_id"],
    )


def downgrade() -> None:
    """Remove project invite storage."""
    op.drop_index("ix_project_invite_project", table_name="project_invites")
    op.drop_table("project_invites")
