"""Persist paper page text for text-derived diagrams."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_paper_texts"
down_revision: str | None = "0010_paper_figures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent paper text storage for diagram extraction."""
    op.create_table(
        "paper_texts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "graph_id",
            "source_id",
            name="uq_paper_text_project_graph_source",
        ),
    )
    op.create_index(
        "ix_paper_text_source",
        "paper_texts",
        ["source_id"],
    )


def downgrade() -> None:
    """Remove paper text storage."""
    op.drop_index("ix_paper_text_source", table_name="paper_texts")
    op.drop_table("paper_texts")
