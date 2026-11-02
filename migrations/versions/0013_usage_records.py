"""Persist per-call model and execution usage for spend tracking."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_usage_records"
down_revision: str | None = "0012_user_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create persistent usage-ledger storage."""
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd_estimated", sa.Float(), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("graph_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_usage_record_created", "usage_records", ["created_at"])
    op.create_index("ix_usage_record_run", "usage_records", ["run_id"])


def downgrade() -> None:
    """Drop usage-ledger storage."""
    op.drop_index("ix_usage_record_run", table_name="usage_records")
    op.drop_index("ix_usage_record_created", table_name="usage_records")
    op.drop_table("usage_records")
