"""Create durable background-job storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_job_queue"
down_revision: str | None = "0007_extracted_tables_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent durable-job storage."""
    op.create_table(
        "job_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_job_queue_job_id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_job_queue_idempotency_key"
        ),
    )
    op.create_index(
        "ix_job_queue_claim", "job_queue", ["state", "available_at"]
    )
    op.create_index("ix_job_queue_kind", "job_queue", ["kind"])


def downgrade() -> None:
    """Remove durable-job storage."""
    op.drop_index("ix_job_queue_kind", table_name="job_queue")
    op.drop_index("ix_job_queue_claim", table_name="job_queue")
    op.drop_table("job_queue")
