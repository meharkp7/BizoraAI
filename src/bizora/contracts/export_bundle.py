"""Portable export bundle for one graph revision.

A bundle is the reproducible artifact of a graph: the full latest
revision plus the project memory facts that explain its choices.
It downloads as a single JSON attachment and re-imports nowhere
yet; the version field guards future import compatibility.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.memory import MemoryFact

BUNDLE_VERSION = "1.0"


class ExportBundle(BaseModel):
    """One self-describing export of a graph and its project memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str = Field(default=BUNDLE_VERSION, min_length=1, max_length=16)
    exported_at: datetime
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    graph: MethodologyGraph
    memory: tuple[MemoryFact, ...] = ()
