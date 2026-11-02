
"""Contracts for spend visibility: daily summaries and per-run costs."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class UsageDay(BaseModel):
    """One UTC day of model and execution spend, all values estimated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: str = Field(min_length=10, max_length=10)
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_estimated: float = Field(ge=0.0)
    unmetered_calls: int = Field(ge=0)


class UsageTotals(BaseModel):
    """Totals across the summary window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_estimated: float = Field(ge=0.0)
    unmetered_calls: int = Field(ge=0)


class UsageCaps(BaseModel):
    """The enforced caps behind the summary (0 disables)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    daily_cap_usd: float = Field(ge=0.0)
    run_cap_usd: float = Field(ge=0.0)
    max_runs_per_day: int = Field(ge=0)


class UsageSummary(BaseModel):
    """Estimated spend per day plus the caps that bound it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: AwareDatetime
    currency: str = "USD"
    estimated: bool = True
    days: list[UsageDay] = Field(default_factory=list)
    totals: UsageTotals
    caps: UsageCaps


class RunUsage(BaseModel):
    """Estimated cost for one run; null cost means unmetered, not free."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    graph_id: str | None = Field(default=None, max_length=128)
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_estimated: float | None = Field(default=None, ge=0.0)
    unmetered: bool = False
    last_used_at: AwareDatetime | None = None
