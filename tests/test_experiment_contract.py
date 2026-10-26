"""Tests for reproducible experiment specification contracts."""

import pytest
from pydantic import ValidationError

from bizora.contracts.experiment import (
    DatasetSplit,
    ExperimentConfig,
    ResultKind,
)


def valid_experiment_data() -> dict[str, object]:
    """Return a valid experiment configuration payload."""
    return {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "hf-vit-classification",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {
            "train": 0.8,
            "validation": 0.1,
            "test": 0.1,
        },
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 1,
    }


def test_dataset_split_accepts_valid_proportions() -> None:
    split = DatasetSplit(train=0.8, validation=0.1, test=0.1)

    assert split.train == 0.8
    assert split.validation == 0.1
    assert split.test == 0.1


def test_dataset_split_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must sum to 1"):
        DatasetSplit(train=0.8, validation=0.1, test=0.2)


@pytest.mark.parametrize(
    ("train", "validation", "test"),
    [
        (0.0, 0.2, 0.8),
        (0.8, -0.1, 0.3),
        (0.8, 0.2, 0.0),
        (1.0, 0.0, 0.0),
    ],
)
def test_dataset_split_rejects_invalid_proportions(
    train: float,
    validation: float,
    test: float,
) -> None:
    with pytest.raises(ValidationError):
        DatasetSplit(
            train=train,
            validation=validation,
            test=test,
        )


def test_experiment_requires_reproducibility_fields() -> None:
    config = ExperimentConfig.model_validate(valid_experiment_data())

    assert config.experiment_id == "exp-1"
    assert config.graph_version == 1
    assert config.seed == 42
    assert config.dataset_revision == "sha256:example"
    assert config.code_revision == "abcdef1"
    assert config.network_access is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("graph_version", 0),
        ("seed", -1),
        ("seed", 2**32),
        ("epochs", 0),
        ("epochs", 1001),
        ("batch_size", 0),
        ("batch_size", 4097),
        ("learning_rate", 0),
        ("learning_rate", 1.01),
        ("max_runtime_seconds", 29),
        ("max_runtime_seconds", 86401),
        ("max_gpu_count", -1),
        ("max_gpu_count", 9),
        ("code_revision", "short"),
    ],
)
def test_experiment_rejects_invalid_bounds(
    field: str,
    value: object,
) -> None:
    payload = valid_experiment_data()
    payload[field] = value

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(payload)


def test_experiment_rejects_unexpected_fields() -> None:
    payload = valid_experiment_data()
    payload["unreviewed_setting"] = True

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(payload)


def test_experiment_configuration_is_immutable() -> None:
    config = ExperimentConfig.model_validate(valid_experiment_data())

    with pytest.raises(ValidationError):
        config.__setattr__("seed", 123)

    with pytest.raises(ValidationError):
        config.split.__setattr__("train", 0.7)

def test_result_kind_labels_are_explicit() -> None:
    assert ResultKind.MEASURED.value == "measured"
    assert ResultKind.ESTIMATED.value == "estimated"
    assert ResultKind.HYPOTHESIS.value == "hypothesis"