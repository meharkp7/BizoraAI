"""Create visual-only graph layout storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_graph_layouts"
down_revision: str | None = "0004_result_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent graph layout storage."""
    op.create_table(
        "graph_layouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("layout_payload", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "graph_id",
            "version",
            name="uq_graph_layout_project_graph_version",
        ),
    )


def downgrade() -> None:
    """Remove graph layout storage."""
    op.drop_table("graph_layouts")
