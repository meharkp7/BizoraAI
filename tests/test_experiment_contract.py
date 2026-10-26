import pytest
from pydantic import ValidationError

from bizora.contracts.experiment import DatasetSplit, ExperimentConfig


def test_dataset_split_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must sum to 1"):
        DatasetSplit(train=0.8, validation=0.1, test=0.2)


def test_experiment_requires_reproducibility_fields() -> None:
    config = ExperimentConfig(
        experiment_id="exp-1", project_id="project-1", graph_id="graph-1", graph_version=1,
        adapter_id="hf-vit-classification", adapter_version="0.1.0", dataset_id="cifar10-subset",
        dataset_revision="sha256:example", seed=42, epochs=3, batch_size=32, learning_rate=0.001,
        split=DatasetSplit(train=0.8, validation=0.1, test=0.1), code_revision="abcdef1",
        max_runtime_seconds=1800, max_gpu_count=1,
    )
    assert config.seed == 42
    assert config.network_access is False


def test_experiment_rejects_unbounded_or_invalid_hyperparameters() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig(
            experiment_id="exp-1", project_id="project-1", graph_id="graph-1", graph_version=1,
            adapter_id="hf-vit-classification", adapter_version="0.1.0", dataset_id="cifar10-subset",
            dataset_revision="sha256:example", seed=-1, epochs=3, batch_size=32, learning_rate=0.001,
            split=DatasetSplit(train=0.8, validation=0.1, test=0.1), code_revision="abcdef1",
            max_runtime_seconds=1800, max_gpu_count=1,
        )
