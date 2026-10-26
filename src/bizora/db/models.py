
"""Persistent SQLAlchemy models for Bizora."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bizora.db.base import Base


class GraphRevisionRecord(Base):
    """A persisted snapshot of one methodology graph revision."""

    __tablename__ = "graph_revisions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "graph_id",
            "version",
            name="uq_graph_revision_project_graph_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    graph_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
