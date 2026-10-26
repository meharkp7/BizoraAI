"""Create metric and artifact record tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_result_records"
down_revision: str | None = "0003_run_worker_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent metric and artifact record storage."""
    op.create_table(
        "metric_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("metric_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("result_kind", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "run_id", "metric_id", name="uq_metric_record_run_metric"
        ),
    )
    op.create_index(
        "ix_metric_record_run_id", "metric_records", ["run_id"]
    )
    op.create_table(
        "artifact_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("uri", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("result_kind", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "run_id", "artifact_id", name="uq_artifact_record_run_artifact"
        ),
    )
    op.create_index(
        "ix_artifact_record_run_id", "artifact_records", ["run_id"]
    )


def downgrade() -> None:
    """Remove metric and artifact record storage."""
    op.drop_index("ix_artifact_record_run_id", table_name="artifact_records")
    op.drop_table("artifact_records")
    op.drop_index("ix_metric_record_run_id", table_name="metric_records")
    op.drop_table("metric_records")
