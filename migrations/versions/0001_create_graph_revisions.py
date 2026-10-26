
"""Create the graph revisions table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_graph_revisions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent graph revision storage."""
    op.create_table(
        "graph_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("graph_payload", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "graph_id",
            "version",
            name="uq_graph_revision_project_graph_version",
        ),
    )


def downgrade() -> None:
    """Remove graph revision storage."""
    op.drop_table("graph_revisions")
