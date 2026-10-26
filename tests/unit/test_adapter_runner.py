"""Tests for the out-of-process adapter runner."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from bizora.adapters.runner import main, run_adapter
from bizora.contracts.execution import ExecutionStatus


def valid_request_data() -> dict[str, Any]:
    """Return a request payload for the deterministic test adapter."""
    return {
        "run_id": "run-1",
        "config": {
            "experiment_id": "exp-1",
            "project_id": "project-1",
            "graph_id": "graph-1",
            "graph_version": 1,
            "adapter_id": "bizora.deterministic-test",
            "adapter_version": "0.1.0",
            "dataset_id": "cifar10-subset",
            "dataset_revision": "sha256:example",
            "seed": 42,
            "epochs": 3,
            "batch_size": 32,
            "learning_rate": 0.001,
            "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
            "code_revision": "abcdef1",
            "max_runtime_seconds": 1800,
            "max_gpu_count": 0,
        },
        "graph": {
            "project_id": "project-1",
            "graph_id": "graph-1",
            "version": 1,
            "parent_version": None,
            "title": "Vision Transformer",
            "source_ids": ["paper-1"],
            "nodes": [
                {"id": "input", "kind": "input", "label": "Image"},
                {"id": "encoder", "kind": "model", "label": "Encoder"},
                {"id": "output", "kind": "output", "label": "Predictions"},
            ],
            "edges": [
                {"id": "edge-1", "source": "input", "target": "encoder"},
                {"id": "edge-2", "source": "encoder", "target": "output"},
            ],
            "created_by": "researcher-1",
        },
        "limits": {
            "timeout_seconds": 600,
            "cpu_seconds": 600,
            "soft_rss_mb": 512,
            "max_output_bytes": 1_000_000,
            "kill_grace_seconds": 10,
        },
    }


def write_request(tmp_path: Path) -> tuple[str, str]:
    """Write a request file and return request/result paths."""
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(valid_request_data()), encoding="utf-8")
    return str(request_path), str(result_path)


def test_run_adapter_writes_valid_result(tmp_path: Path) -> None:
    request_path, result_path = write_request(tmp_path)

    result = run_adapter(request_path, result_path)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.run_id == "run-1"
    stored = json.loads(Path(result_path).read_text(encoding="utf-8"))
    assert stored["run_id"] == "run-1"
    assert stored["status"] == ExecutionStatus.SUCCEEDED.value


def test_main_returns_zero_on_success(tmp_path: Path) -> None:
    request_path, result_path = write_request(tmp_path)

    assert main(["runner", request_path, result_path]) == 0


def test_main_rejects_bad_arguments(tmp_path: Path) -> None:
    assert main(["runner"]) == 2
    assert main(["runner", str(tmp_path)]) == 2


def test_main_fails_for_unknown_adapter(tmp_path: Path) -> None:
    payload = valid_request_data()
    config = dict(payload["config"])
    config["adapter_id"] = "bizora.unknown"
    payload["config"] = config
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["runner", str(request_path), str(result_path)]) == 2
    assert not result_path.exists()


def test_main_fails_for_missing_request(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"

    assert (
        main(["runner", str(tmp_path / "absent.json"), str(result_path)]) == 2
    )
    assert not result_path.exists()


def test_runner_executes_as_subprocess(tmp_path: Path) -> None:
    request_path, result_path = write_request(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "bizora.adapters.runner",
            request_path,
            result_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0
    stored = json.loads(Path(result_path).read_text(encoding="utf-8"))
    assert stored["status"] == ExecutionStatus.SUCCEEDED.value
    assert stored["echo"]["seed"] == 42
