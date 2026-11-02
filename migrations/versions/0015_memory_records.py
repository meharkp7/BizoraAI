"""Create project memory storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_memory_records"
down_revision: str | None = "0014_copilot_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent project memory storage."""
    op.create_table(
        "memory_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_record_project",
        "memory_records",
        ["project_id"],
    )


def downgrade() -> None:
    """Remove project memory storage."""
    op.drop_index("ix_memory_record_project", table_name="memory_records")
    op.drop_table("memory_records")
