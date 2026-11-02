"""Project memory contracts.

Memory facts are short notes the copilot stores ("remember ...") and
recalls on later turns. They belong to a project, not a graph, so
every paper in the project shares them.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    """Record one memory fact on a project."""

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1, max_length=500)
    created_by: str = Field(min_length=1, max_length=128)


class MemoryFact(BaseModel):
    """One stored memory fact, newest first in listings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=1)
    project_id: str = Field(min_length=1, max_length=128)
    fact: str = Field(min_length=1, max_length=500)
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
