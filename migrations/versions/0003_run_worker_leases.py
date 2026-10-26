"""Add worker lease columns to experiment runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_run_worker_leases"
down_revision: str | None = "0002_experiment_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable worker ownership and lease expiry columns."""
    op.add_column(
        "experiment_runs",
        sa.Column("worker_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "experiment_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_experiment_run_state_lease",
        "experiment_runs",
        ["state", "lease_expires_at"],
    )


def downgrade() -> None:
    """Remove worker lease columns from experiment runs."""
    op.drop_index(
        "ix_experiment_run_state_lease",
        table_name="experiment_runs",
    )
    op.drop_column("experiment_runs", "lease_expires_at")
    op.drop_column("experiment_runs", "worker_id")
