"""Create user accounts, paper libraries, and notes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_user_accounts"
down_revision: str | None = "0011_paper_texts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent account, library, and note storage."""
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "user_papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            name="uq_user_paper_user_project",
        ),
    )
    op.create_index("ix_user_paper_user", "user_papers", ["user_id"])
    op.create_table(
        "paper_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("paper_id", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_paper_note_user_paper", "paper_notes", ["user_id", "paper_id"]
    )


def downgrade() -> None:
    """Remove account, library, and note storage."""
    op.drop_index("ix_paper_note_user_paper", table_name="paper_notes")
    op.drop_table("paper_notes")
    op.drop_index("ix_user_paper_user", table_name="user_papers")
    op.drop_table("user_papers")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
