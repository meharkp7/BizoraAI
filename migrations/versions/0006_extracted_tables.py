"""Create extracted results-table storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_extracted_tables"
down_revision: str | None = "0005_graph_layouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent extracted-table storage."""
    op.create_table(
        "extracted_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("table_payload", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "graph_id",
            "table_id",
            name="uq_extracted_table_project_graph_table",
        ),
    )


def downgrade() -> None:
    """Remove extracted-table storage."""
    op.drop_table("extracted_tables")
