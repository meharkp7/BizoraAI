
"""Contracts for the extraction-quality dashboard."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DiagramEvalSummary(BaseModel):
    """One committed diagram-eval report, reduced to dashboard numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str = Field(min_length=1, max_length=128)
    recorded_at: AwareDatetime
    validator_pass_rate: float = Field(ge=0.0, le=1.0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    gold_present: bool = False
    classification_kind: str | None = Field(default=None, max_length=64)


class CopilotEvalSummary(BaseModel):
    """The last copilot eval run, reduced to dashboard numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    citation_accuracy: float = Field(ge=0.0, le=1.0)
    citation_recall: float = Field(ge=0.0, le=1.0)
    writes_detected: bool = False
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    recorded_at: AwareDatetime


class QualitySummary(BaseModel):
    """Everything the quality dashboard renders, with its freshness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: AwareDatetime
    diagram_evals: list[DiagramEvalSummary] = Field(default_factory=list)
    copilot_eval: CopilotEvalSummary | None = None
