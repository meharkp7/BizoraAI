"""Persistent model for project membership."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bizora.db.base import Base


class ProjectMemberRow(Base):
    """One user's explicit membership in one project."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_member_project_user",
        ),
        Index("ix_project_member_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
