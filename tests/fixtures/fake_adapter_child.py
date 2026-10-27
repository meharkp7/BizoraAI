"""Synthetic adapter child for execution-supervision tests.

Usage: fake_adapter_child.py <mode> <request.json> <result.json> [extra...]

Modes: ok, slow, crash, spam, badjson, silent, env, metrics,
failedmetrics, nanmetrics. No network, no imports beyond the standard
library, no effects outside the given paths.
"""

import json
import os
import sys
import time


def _echo_for(request: dict[str, object]) -> dict[str, object]:
    config = request["config"]
    assert isinstance(config, dict)
    return {
        "adapter_id": config["adapter_id"],
        "adapter_version": config["adapter_version"],
        "dataset_id": config["dataset_id"],
        "dataset_revision": config["dataset_revision"],
        "code_revision": config["code_revision"],
        "seed": config["seed"],
        "graph_id": config["graph_id"],
        "graph_version": config["graph_version"],
    }


def _write_ok(request: dict[str, object], result_path: str) -> None:
    result = {
        "run_id": request["run_id"],
        "status": "succeeded",
        "echo": _echo_for(request),
        "diagnostics": ["fake adapter ok"],
    }
    with open(result_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result))


def main(argv: list[str]) -> int:
    mode, request_path, result_path = argv[1], argv[2], argv[3]
    extra = argv[4:]
    with open(request_path, encoding="utf-8") as handle:
        request = json.load(handle)

    if mode == "ok":
        _write_ok(request, result_path)
        return 0
    if mode == "slow":
        time.sleep(float(extra[0]))
        _write_ok(request, result_path)
        return 0
    if mode == "crash":
        print("fake adapter crashed", file=sys.stderr)
        return int(extra[0]) if extra else 3
    if mode == "spam":
        sys.stdout.write("x" * int(extra[0]))
        sys.stdout.flush()
        _write_ok(request, result_path)
        return 0
    if mode == "badjson":
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        return 0
    if mode == "silent":
        return 0
    if mode == "env":
        with open(extra[0], "w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(os.environ), sort_keys=True))
        _write_ok(request, result_path)
        return 0
    if mode == "metrics":
        result = {
            "run_id": request["run_id"],
            "status": "succeeded",
            "echo": _echo_for(request),
            "diagnostics": ["fake adapter ok"],
            "metrics": [
                {
                    "metric_id": "metric-accuracy",
                    "name": "accuracy",
                    "value": 0.92,
                    "result_kind": "measured",
                }
            ],
            "artifacts": [
                {
                    "artifact_id": "artifact-checkpoint",
                    "kind": "checkpoint",
                    "uri": "file:///tmp/fake-checkpoint",
                    "sha256": "b" * 64,
                    "result_kind": "measured",
                }
            ],
        }
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(result))
        return 0
    if mode == "nanmetrics":
        result = {
            "run_id": request["run_id"],
            "status": "succeeded",
            "echo": _echo_for(request),
            "diagnostics": ["fake adapter ok"],
            "metrics": [
                {
                    "metric_id": "metric-nan",
                    "name": "not-a-number",
                    "value": float("nan"),
                    "result_kind": "measured",
                }
            ],
        }
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(result, allow_nan=True))
        return 0
    if mode == "failedmetrics":
        result = {
            "run_id": request["run_id"],
            "status": "failed",
            "echo": _echo_for(request),
            "diagnostics": ["fake adapter failed"],
            "metrics": [
                {
                    "metric_id": "metric-partial",
                    "name": "partial",
                    "value": 0.5,
                    "result_kind": "measured",
                }
            ],
            "error": {
                "code": "adapter_failed",
                "message": "Fake adapter failed after partial work.",
            },
        }
        with open(result_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(result))
        return 0
    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
