"""Experiment specification and result-label contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResultKind(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    HYPOTHESIS = "hypothesis"


class DatasetSplit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train: float = Field(gt=0, lt=1)
    validation: float = Field(ge=0, lt=1)
    test: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def splits_sum_to_one(self) -> "DatasetSplit":
        if abs((self.train + self.validation + self.test) - 1.0) > 1e-6:
            raise ValueError("train, validation, and test split proportions must sum to 1")
        return self


class ExperimentConfig(BaseModel):
    """Reproducibility-oriented run specification, independent of a compute provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    graph_version: int = Field(ge=1)
    adapter_id: str = Field(min_length=1, max_length=128)
    adapter_version: str = Field(min_length=1, max_length=64)
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_revision: str = Field(min_length=1, max_length=128)
    seed: int = Field(ge=0, le=2**32 - 1)
    epochs: int = Field(ge=1, le=1000)
    batch_size: int = Field(ge=1, le=4096)
    learning_rate: float = Field(gt=0, le=1)
    split: DatasetSplit
    code_revision: str = Field(min_length=7, max_length=64)
    max_runtime_seconds: int = Field(ge=30, le=86_400)
    max_gpu_count: int = Field(ge=0, le=8)
    network_access: bool = False
