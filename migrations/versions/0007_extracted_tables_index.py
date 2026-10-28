"""Add the extracted-tables project/graph lookup index."""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_extracted_tables_index"
down_revision: str | None = "0006_extracted_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the index declared by the extracted-table model."""
    op.create_index(
        "ix_extracted_table_project_graph",
        "extracted_tables",
        ["project_id", "graph_id"],
    )


def downgrade() -> None:
    """Remove the extracted-tables project/graph lookup index."""
    op.drop_index(
        "ix_extracted_table_project_graph",
        table_name="extracted_tables",
    )
