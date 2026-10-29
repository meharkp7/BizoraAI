
"""Persistent SQLAlchemy models for Bizora."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
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


class GraphLayoutRecord(Base):
    """A persisted visual-only layout bound to one graph revision.

    Layouts are mutable per revision and never affect graph semantics;
    saving a layout must not create a graph revision.
    """

    __tablename__ = "graph_layouts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "graph_id",
            "version",
            name="uq_graph_layout_project_graph_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)

    layout_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ExperimentRunRecord(Base):
    """A persisted experiment run bound to one exact graph revision."""

    __tablename__ = "experiment_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_experiment_run_run_id"),
        Index(
            "ix_experiment_run_project_graph_version",
            "project_id",
            "graph_id",
            "graph_version",
        ),
        Index(
            "ix_experiment_run_state_lease",
            "state",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    experiment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class MetricRecordRow(Base):
    """A persisted metric value linked to one exact experiment run."""

    __tablename__ = "metric_records"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "metric_id",
            name="uq_metric_record_run_metric",
        ),
        Index("ix_metric_record_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    result_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class ArtifactRecordRow(Base):
    """A persisted artifact reference linked to one exact experiment run."""

    __tablename__ = "artifact_records"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "artifact_id",
            name="uq_artifact_record_run_artifact",
        ),
        Index("ix_artifact_record_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class ExtractedTableRecord(Base):
    """A persisted results table extracted from a paper."""

    __tablename__ = "extracted_tables"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "graph_id",
            "table_id",
            name="uq_extracted_table_project_graph_table",
        ),
        Index("ix_extracted_table_project_graph", "project_id", "graph_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    table_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    table_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PaperFigureRecord(Base):
    """A persisted paper figure: trusted metadata, regions, and image bytes."""

    __tablename__ = "paper_figures"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "graph_id",
            "figure_id",
            name="uq_paper_figure_project_graph_figure",
        ),
        Index("ix_paper_figure_project_graph", "project_id", "graph_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    figure_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    regions_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
