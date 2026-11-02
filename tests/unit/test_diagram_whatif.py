"""Unit + contract tests for methodology what-if evaluation."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_diagram_extraction import (
    ScriptedDiagramProvider,
    make_circuit_payload,
    make_methodology_payload,
    make_structure_payload,
)
from tests.unit.test_diagrams_api import seed_paper_with_figures
from tests.unit.test_figure_service import StubVisionProvider

from bizora.api import get_diagram_provider, get_muse_provider
from bizora.contracts.diagram_ir import MethodologyNode
from bizora.core.diagram_whatif import (
    WHATIF_PROMPT_VERSION,
    WhatIfResult,
    check_whatif_params,
    load_cached_whatif,
    run_what_if,
    save_cached_whatif,
    whatif_cache_key,
    whatif_prompt,
)
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app


def make_node(**overrides: Any) -> MethodologyNode:
    payload: dict[str, Any] = {
        "id": "n1",
        "label": "load",
        "kind": "input",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return MethodologyNode.model_validate(payload)


def test_check_params_strips_and_passes_through() -> None:
    assert check_whatif_params({" epochs ": " 50 "}) == {"epochs": "50"}


def test_check_params_rejects_empty() -> None:
    with pytest.raises(ValueError, match="At least one"):
        check_whatif_params({})


def test_check_params_rejects_blank_name_and_value() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        check_whatif_params({"  ": "50"})
    with pytest.raises(ValueError, match="non-empty"):
        check_whatif_params({"epochs": "  "})


def test_check_params_rejects_too_many_and_too_long() -> None:
    with pytest.raises(ValueError, match="At most"):
        check_whatif_params({f"k{i}": "v" for i in range(33)})
    with pytest.raises(ValueError, match="too long"):
        check_whatif_params({"epochs": "x" * 257})


def test_cache_key_ignores_param_order() -> None:
    first = whatif_cache_key("hash", "n1", {"a": "1", "b": "2"})
    second = whatif_cache_key("hash", "n1", {"b": "2", "a": "1"})
    assert first == second
    assert first.endswith(f"-w{WHATIF_PROMPT_VERSION}")
    assert whatif_cache_key("hash", "n1", {"a": "1"}) != first


def test_cache_roundtrip_and_version_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path))
    assert load_cached_whatif("nope") is None
    result = WhatIfResult(
        node_id="n1",
        node_label="load",
        params_previous={},
        params_applied={"epochs": "50"},
        outcome="Estimated stub.",
        basis=(),
        assumptions=(),
        confidence=0.5,
    )
    save_cached_whatif("key-w1", result)
    assert load_cached_whatif("key-w1") == result
    stale = tmp_path / "whatif" / "key-w1.json"
    payload = json.loads(stale.read_text(encoding="utf-8"))
    payload["prompt_version"] = 999
    stale.write_text(json.dumps(payload), encoding="utf-8")
    assert load_cached_whatif("key-w1") is None


def test_prompt_carries_step_context() -> None:
    node = make_node(
        detail="loads data",
        params={"batch": "32"},
        evidence={"page": 3, "figure_id": None, "quote": "loads in batches"},
    )
    prompt = whatif_prompt(node, {"batch": "64"}, "[Page 3] loads in batches.")
    assert "load (n1)" in prompt
    assert "batch: 32" in prompt
    assert "batch: 64" in prompt
    assert "[Page 3]" in prompt
    assert "loads data" in prompt


def test_prompt_handles_missing_context() -> None:
    prompt = whatif_prompt(make_node(), {"batch": "64"}, "text")
    assert "(none stated)" in prompt
    assert "Step evidence" not in prompt


@pytest.fixture
def stub_whatif() -> ScriptedDiagramProvider:
    return ScriptedDiagramProvider()


@pytest.fixture
def client(
    stub_whatif: ScriptedDiagramProvider,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path))
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_muse_provider] = StubVisionProvider
    app.dependency_overrides[get_diagram_provider] = lambda: stub_whatif

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_muse_provider, None)
        app.dependency_overrides.pop(get_diagram_provider, None)
        engine.dispose()


def script_flow(
    stub: ScriptedDiagramProvider, figure_ids: list[str], methodology: dict[str, Any]
) -> None:
    for figure_id in figure_ids:
        stub.figure_payloads[(figure_id, "circuit")] = make_circuit_payload()
    stub.text_payloads["methodology"] = methodology
    stub.text_payloads["structure"] = make_structure_payload()


def test_whatif_response_contract(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_payload())

    response = client.post(
        "/api/v1/papers/paper-9/whatif",
        json={"node_id": "n2", "params": {"epochs": "50"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "node_id",
        "node_label",
        "params_previous",
        "params_applied",
        "outcome",
        "basis",
        "assumptions",
        "confidence",
        "from_cache",
    }
    assert body["node_id"] == "n2"
    assert body["node_label"] == "train"
    assert body["params_applied"] == {"epochs": "50"}
    assert body["basis"] == [{"quote": "stub quote", "page": 2}]
    assert body["from_cache"] is False


def test_whatif_reports_previous_params(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    methodology = make_methodology_payload()
    methodology["nodes"][0]["params"] = {"lr": "0.01"}
    script_flow(stub_whatif, figure_ids, methodology)

    response = client.post(
        "/api/v1/papers/paper-9/whatif",
        json={"node_id": "n1", "params": {"lr": "0.05"}},
    )

    assert response.status_code == 200
    assert response.json()["params_previous"] == {"lr": "0.01"}


def test_whatif_caches_repeat_runs(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_payload())
    payload = {"node_id": "n2", "params": {"epochs": "50"}}

    assert client.post("/api/v1/papers/paper-9/whatif", json=payload).json()[
        "from_cache"
    ] is False
    assert client.post("/api/v1/papers/paper-9/whatif", json=payload).json()[
        "from_cache"
    ] is True
    assert stub_whatif.calls.get("whatif") == 1


def test_whatif_unknown_node_and_paper(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_payload())

    missing = client.post(
        "/api/v1/papers/paper-9/whatif",
        json={"node_id": "zzz", "params": {"epochs": "50"}},
    )
    assert missing.status_code == 404
    nopaper = client.post(
        "/api/v1/papers/paper-zzz/whatif",
        json={"node_id": "n1", "params": {"epochs": "50"}},
    )
    assert nopaper.status_code == 404


def test_whatif_rejects_bad_params(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_payload())

    empty = client.post(
        "/api/v1/papers/paper-9/whatif", json={"node_id": "n1", "params": {}}
    )
    assert empty.status_code == 422
    blank = client.post(
        "/api/v1/papers/paper-9/whatif",
        json={"node_id": "n1", "params": {"epochs": "  "}},
    )
    assert blank.status_code == 400


def test_whatif_provider_failure_is_bad_gateway(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_payload())
    stub_whatif.fail_whatif = True

    response = client.post(
        "/api/v1/papers/paper-9/whatif",
        json={"node_id": "n1", "params": {"epochs": "50"}},
    )

    assert response.status_code == 502


def test_run_what_if_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async def run_test() -> None:
        stub = ScriptedDiagramProvider()
        node = make_node(params={"lr": "0.01"})

        first, cached_first = await run_what_if(
            stub, "hash", node, {"lr": "0.05"}, "paper text"
        )
        second, cached_second = await run_what_if(
            stub, "hash", node, {"lr": "0.05"}, "paper text"
        )

        assert cached_first is False
        assert cached_second is True
        assert first == second
        assert stub.calls.get("whatif") == 1

    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path))
    asyncio.run(run_test())


def make_methodology_with_params() -> dict[str, Any]:
    """Build a methodology flow whose train step exposes settings."""
    payload = make_methodology_payload()
    payload["nodes"][1]["params"] = {"epochs": 50, "batch": 32}
    return payload


def test_parse_plain_english_resolves_step_and_settings(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_with_params())

    response = client.post(
        "/api/v1/papers/paper-9/whatif/parse",
        json={"text": "what if train epochs were 100?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "node_id": "n2",
        "node_label": "train",
        "params": {"epochs": "100"},
    }


def test_parse_uses_context_step_when_unnamed(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_with_params())

    response = client.post(
        "/api/v1/papers/paper-9/whatif/parse",
        json={"text": "epochs to 100 and batch to 64", "node_id": "n2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["node_id"] == "n2"
    assert body["params"] == {"epochs": "100", "batch": "64"}


def test_parse_ambiguity_explains_instead_of_guessing(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-9")
    script_flow(stub_whatif, figure_ids, make_methodology_with_params())

    response = client.post(
        "/api/v1/papers/paper-9/whatif/parse",
        json={"text": "epochs to 100"},
    )

    assert response.status_code == 422
    assert "Which step?" in response.json()["error"]["message"]


def test_parse_unknown_paper_returns_404(
    client: TestClient, stub_whatif: ScriptedDiagramProvider
) -> None:
    response = client.post(
        "/api/v1/papers/paper-missing/whatif/parse",
        json={"text": "epochs to 100", "node_id": "n2"},
    )

    assert response.status_code == 404
