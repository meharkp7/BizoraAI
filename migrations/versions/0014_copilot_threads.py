"""Create copilot thread and turn storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_copilot_threads"
down_revision: str | None = "0013_usage_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent copilot conversation storage."""
    op.create_table(
        "copilot_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
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
        sa.UniqueConstraint("thread_id", name="uq_copilot_thread_thread_id"),
    )
    op.create_index(
        "ix_copilot_thread_project_graph",
        "copilot_threads",
        ["project_id", "graph_id"],
    )
    op.create_table(
        "copilot_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "thread_id",
            "seq",
            name="uq_copilot_turn_thread_seq",
        ),
    )
    op.create_index(
        "ix_copilot_turn_thread",
        "copilot_turns",
        ["thread_id"],
    )


def downgrade() -> None:
    """Remove copilot conversation storage."""
    op.drop_index("ix_copilot_turn_thread", table_name="copilot_turns")
    op.drop_table("copilot_turns")
    op.drop_index("ix_copilot_thread_project_graph", table_name="copilot_threads")
    op.drop_table("copilot_threads")
