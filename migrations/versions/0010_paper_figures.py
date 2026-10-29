"""Create paper figure overlay storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_paper_figures"
down_revision: str | None = "0009_project_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent paper figure storage with regions and bytes."""
    op.create_table(
        "paper_figures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("figure_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("regions_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "graph_id",
            "figure_id",
            name="uq_paper_figure_project_graph_figure",
        ),
    )
    op.create_index(
        "ix_paper_figure_project_graph",
        "paper_figures",
        ["project_id", "graph_id"],
    )


def downgrade() -> None:
    """Remove paper figure overlay storage."""
    op.drop_index("ix_paper_figure_project_graph", table_name="paper_figures")
    op.drop_table("paper_figures")
