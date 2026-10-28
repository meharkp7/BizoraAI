"""Tests for the extraction correction loop.

Covers: assumed flags applied at extraction time, visible persistence of
those flags, and corrections (accept/edit/reject) applied as new graph
revisions through the existing patch machinery.

All providers, graphs, and patches below are clearly-marked fakes. No
network calls, no live providers; persistence uses an in-memory SQLite
database owned by each test.
"""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.contracts.assumptions import (
    ASSUMED_CONFIG_KEY,
    ASSUMPTION_REASON_CONFIG_KEY,
    DEFAULT_ASSUMPTION_REASON,
    clear_assumed,
    node_assumption_reason,
    node_is_assumed,
    summarize_assumptions,
)
from bizora.contracts.evidence import EvidenceRef, EvidenceStatus, Provenance
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.patches import GraphPatch, PatchOperation
from bizora.core.extraction_persistence_service import (
    ExtractionPersistenceService,
)
from bizora.core.extraction_service import MethodologyExtractionService
from bizora.core.graph_persistence_service import GraphPersistenceService
from bizora.core.patch_service import GraphPatchService
from bizora.db.base import Base
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)


class FakeAssumedProvider:
    """Fake provider returning a predetermined draft (no network)."""

    def __init__(self, graph: MethodologyGraph) -> None:
        self.graph = graph

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        return MethodologyExtractionResult(
            draft_graph=self.graph,
            provider_name="fake-correction-provider",
            model_name="fake-model",
        )


def make_fake_request() -> MethodologyExtractionRequest:
    """Fake fixture: one extraction request for a fake paper."""
    return MethodologyExtractionRequest(
        paper_text="The fake paper describes a fake widget.",
        project_id="fake-correction-project",
        graph_id="fake-correction-graph",
        source_id="fake-correction-paper",
        created_by="fake-user",
        title="Fake correction methodology",
    )


def make_fake_evidenced_node() -> GraphNode:
    """Fake fixture: a component grounded in the fake paper."""
    return GraphNode(
        id="fake-evidenced",
        kind=NodeKind.COMPONENT,
        label="Fake evidenced widget",
        evidence=(
            EvidenceRef(
                source_id="fake-correction-paper",
                page=2,
                quote="The widget processes the input.",
                status=EvidenceStatus.SUPPORTED,
            ),
        ),
        provenance=Provenance.EXTRACTED,
    )


def make_fake_bare_node() -> GraphNode:
    """Fake fixture: a component with neither evidence nor flags."""
    return GraphNode(
        id="fake-bare",
        kind=NodeKind.COMPONENT,
        label="Fake ungrounded widget",
    )


def make_fake_draft() -> MethodologyGraph:
    """Fake fixture: a provider draft mixing grounded and bare claims."""
    return MethodologyGraph(
        schema_version="1.0",
        project_id="fake-correction-project",
        graph_id="fake-correction-graph",
        version=1,
        title="Fake correction methodology",
        source_ids=("fake-correction-paper",),
        nodes=(make_fake_evidenced_node(), make_fake_bare_node()),
        edges=(
            GraphEdge(
                id="fake-edge",
                source="fake-evidenced",
                target="fake-bare",
            ),
        ),
        created_by="fake-user",
    )


@pytest.fixture
def session() -> Iterator[Session]:
    """Fake persistence: an in-memory database owned by the test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db_session:
            yield db_session
    finally:
        engine.dispose()


def test_extract_draft_marks_ungrounded_claims_as_assumed() -> None:
    async def run_test() -> None:
        request = make_fake_request()
        draft = await MethodologyExtractionService.extract_draft(
            FakeAssumedProvider(make_fake_draft()),
            request,
        )

        by_id = {node.id: node for node in draft.nodes}
        assert node_is_assumed(by_id["fake-evidenced"]) is False
        assert node_is_assumed(by_id["fake-bare"]) is True
        assert node_assumption_reason(by_id["fake-bare"]) == DEFAULT_ASSUMPTION_REASON
        assert by_id["fake-bare"].provenance == Provenance.INFERRED
        assert summarize_assumptions(draft).complete is True

    asyncio.run(run_test())


def test_extract_draft_preserves_explicit_provider_reasons() -> None:
    async def run_test() -> None:
        draft_graph = make_fake_draft()
        nodes = list(draft_graph.nodes)
        nodes[1] = nodes[1].model_copy(
            update={
                "config": {
                    ASSUMED_CONFIG_KEY: True,
                    ASSUMPTION_REASON_CONFIG_KEY: "Fake provider reason.",
                }
            }
        )
        draft_graph = draft_graph.model_copy(update={"nodes": tuple(nodes)})

        draft = await MethodologyExtractionService.extract_draft(
            FakeAssumedProvider(draft_graph),
            make_fake_request(),
        )

        by_id = {node.id: node for node in draft.nodes}
        assert node_assumption_reason(by_id["fake-bare"]) == "Fake provider reason."

    asyncio.run(run_test())


def test_extract_and_persist_keeps_assumed_flags_visible(
    session: Session,
) -> None:
    async def run_test() -> None:
        persisted = await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            FakeAssumedProvider(make_fake_draft()),
            make_fake_request(),
        )

        by_id = {node.id: node for node in persisted.nodes}
        assert node_is_assumed(by_id["fake-bare"]) is True
        assert node_assumption_reason(by_id["fake-bare"]) == DEFAULT_ASSUMPTION_REASON
        # The stored payload itself carries the visible marking.
        stored_config = by_id["fake-bare"].config
        assert stored_config[ASSUMED_CONFIG_KEY] is True
        assert ASSUMPTION_REASON_CONFIG_KEY in stored_config

    asyncio.run(run_test())


def _accept_patch(graph: MethodologyGraph, node_id: str) -> GraphPatch:
    """Fake fixture: an accept correction clearing the assumed flag."""
    node = next(item for item in graph.nodes if item.id == node_id)
    cleared = clear_assumed(node)
    return GraphPatch(
        patch_id=f"fake-accept-{node_id}",
        base_graph_id=graph.graph_id,
        base_version=graph.version,
        operation=PatchOperation.REPLACE_NODE,
        target_id=node_id,
        payload={"node": cleared.model_dump(mode="json")},
        rationale=f"Fake reviewer accepts {node_id}.",
        requested_by="fake-reviewer",
    )


def test_accept_correction_persists_as_new_revision(session: Session) -> None:
    async def run_test() -> None:
        persisted = await ExtractionPersistenceService.extract_and_persist_initial(
            session,
            FakeAssumedProvider(make_fake_draft()),
            make_fake_request(),
        )
        assert node_is_assumed(next(n for n in persisted.nodes if n.id == "fake-bare")) is True

        revised = GraphPatchService.apply_patches(
            persisted, [_accept_patch(persisted, "fake-bare")]
        )
        assert revised.version == persisted.version + 1
        assert revised.parent_version == persisted.version

        by_id = {node.id: node for node in revised.nodes}
        assert node_is_assumed(by_id["fake-bare"]) is False
        assert by_id["fake-bare"].provenance == Provenance.VERIFIED
        assert by_id["fake-bare"].label == "Fake ungrounded widget"

        record = GraphPersistenceService.create_revision(
            session,
            persisted,
            created_by="fake-reviewer",
            nodes=revised.nodes,
            edges=revised.edges,
        )
        stored = MethodologyGraph.model_validate(record.graph_payload)
        assert stored.version == 2
        assert node_is_assumed(next(n for n in stored.nodes if n.id == "fake-bare")) is False

    asyncio.run(run_test())


def test_edit_correction_updates_claim_and_clears_flag() -> None:
    async def run_test() -> None:
        draft = await MethodologyExtractionService.extract_draft(
            FakeAssumedProvider(make_fake_draft()),
            make_fake_request(),
        )
        node = next(item for item in draft.nodes if item.id == "fake-bare")
        edited = clear_assumed(node).model_copy(
            update={
                "label": "Fake corrected widget",
                "description": "Fake reviewer correction.",
            }
        )
        patch = GraphPatch(
            patch_id="fake-edit-bare",
            base_graph_id=draft.graph_id,
            base_version=draft.version,
            operation=PatchOperation.REPLACE_NODE,
            target_id="fake-bare",
            payload={"node": edited.model_dump(mode="json")},
            rationale="Fake reviewer corrects the claim.",
            requested_by="fake-reviewer",
        )

        revised = GraphPatchService.apply_patches(draft, [patch])
        assert revised.version == draft.version + 1
        updated = next(item for item in revised.nodes if item.id == "fake-bare")
        assert updated.label == "Fake corrected widget"
        assert updated.description == "Fake reviewer correction."
        assert node_is_assumed(updated) is False

    asyncio.run(run_test())


def test_reject_correction_removes_node_in_new_revision() -> None:
    async def run_test() -> None:
        draft = await MethodologyExtractionService.extract_draft(
            FakeAssumedProvider(make_fake_draft()),
            make_fake_request(),
        )
        # Edges first: a node with connections cannot be removed directly.
        patches = [
            GraphPatch(
                patch_id="fake-reject-edge",
                base_graph_id=draft.graph_id,
                base_version=draft.version,
                operation=PatchOperation.REMOVE_EDGE,
                target_id="fake-edge",
                payload={},
                rationale="Fake reviewer rejects the connection.",
                requested_by="fake-reviewer",
            ),
            GraphPatch(
                patch_id="fake-reject-node",
                base_graph_id=draft.graph_id,
                base_version=draft.version,
                operation=PatchOperation.REMOVE_NODE,
                target_id="fake-bare",
                payload={},
                rationale="Fake reviewer rejects the claim.",
                requested_by="fake-reviewer",
            ),
        ]

        revised = GraphPatchService.apply_patches(draft, patches)
        assert revised.version == draft.version + 1
        assert [node.id for node in revised.nodes] == ["fake-evidenced"]
        assert revised.edges == ()

    asyncio.run(run_test())


def test_mixed_corrections_apply_atomically_as_one_revision() -> None:
    async def run_test() -> None:
        draft = await MethodologyExtractionService.extract_draft(
            FakeAssumedProvider(make_fake_draft()),
            make_fake_request(),
        )
        second = make_fake_bare_node().model_copy(update={"id": "fake-bare-2"})
        draft = draft.model_copy(update={"nodes": (*draft.nodes, second)})

        patches = [
            _accept_patch(draft, "fake-bare"),
            GraphPatch(
                patch_id="fake-reject-node-2",
                base_graph_id=draft.graph_id,
                base_version=draft.version,
                operation=PatchOperation.REMOVE_NODE,
                target_id="fake-bare-2",
                payload={},
                rationale="Fake reviewer rejects the duplicate claim.",
                requested_by="fake-reviewer",
            ),
        ]
        revised = GraphPatchService.apply_patches(draft, patches)

        assert revised.version == draft.version + 1
        assert revised.parent_version == draft.version
        accepted = next(n for n in revised.nodes if n.id == "fake-bare")
        assert node_is_assumed(accepted) is False
        assert "fake-bare-2" not in {n.id for n in revised.nodes}

    asyncio.run(run_test())
