"""Create the experiment runs table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_experiment_runs"
down_revision: str | None = "0001_graph_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent experiment run storage."""
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("experiment_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("graph_id", sa.String(length=128), nullable=False),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", name="uq_experiment_run_run_id"),
    )
    op.create_index(
        "ix_experiment_run_project_graph_version",
        "experiment_runs",
        ["project_id", "graph_id", "graph_version"],
    )


def downgrade() -> None:
    """Remove experiment run storage."""
    op.drop_index(
        "ix_experiment_run_project_graph_version",
        table_name="experiment_runs",
    )
    op.drop_table("experiment_runs")
