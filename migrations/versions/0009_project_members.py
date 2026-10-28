"""Create project membership storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_project_members"
down_revision: str | None = "0008_job_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent project membership storage."""
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_member_project_user",
        ),
    )
    op.create_index("ix_project_member_user", "project_members", ["user_id"])


def downgrade() -> None:
    """Remove project membership storage."""
    op.drop_index("ix_project_member_user", table_name="project_members")
    op.drop_table("project_members")
