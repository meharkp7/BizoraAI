"""Deterministic replication plans derived from methodology graphs.

A replication plan turns a graph into an ordered build checklist: one
step per node in dependency order, each with a concrete action and
verification hints. Plans are fully deterministic (no LLM), so two
exports of the same revision always agree.
"""

from pydantic import BaseModel, ConfigDict, Field


class ReplicationStep(BaseModel):
    """One ordered build-and-verify step for a single graph node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(ge=1)
    node_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=2000)
    verify: tuple[str, ...] = ()


class ReplicationPlan(BaseModel):
    """The full ordered plan for one graph revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    steps: tuple[ReplicationStep, ...]


class NarrationLine(BaseModel):
    """One speakable line of the narrated build guide."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(ge=1)
    node_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class PlanNarration(BaseModel):
    """The full narrated build guide for one graph revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    intro: str = Field(min_length=1, max_length=2000)
    lines: tuple[NarrationLine, ...]
