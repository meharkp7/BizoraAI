import { beforeEach, describe, expect, it } from "vitest";
import type { GraphPatch } from "../../lib/types.ts";
import { activeDraftForGraph, useScenarioDrafts } from "./drafts.ts";

function makePatch(patchId: string): GraphPatch {
  return {
    patch_id: patchId,
    base_graph_id: "graph-1",
    base_version: 2,
    operation: "update_node_config",
    target_id: "encoder",
    payload: { config: { layers: 6 } },
    rationale: "Update encoder configuration",
    requested_by: "workspace-ui",
  };
}

describe("useScenarioDrafts", () => {
  beforeEach(() => {
    useScenarioDrafts.getState().reset();
  });

  it("creates a draft and activates it for staging", () => {
    const draft = useScenarioDrafts.getState().createDraft({
      name: "Scenario 1",
      projectId: "project-1",
      graphId: "graph-1",
      baseVersion: 2,
      baseTitle: "Vision transformer",
    });

    const state = useScenarioDrafts.getState();
    expect(draft.patches).toEqual([]);
    expect(state.drafts).toHaveLength(1);
    expect(state.activeDraftId).toBe(draft.id);
  });

  it("stages and removes patches without touching other drafts", () => {
    const store = useScenarioDrafts.getState();
    const first = store.createDraft({
      name: "Scenario 1",
      projectId: "project-1",
      graphId: "graph-1",
      baseVersion: 2,
      baseTitle: "Vision transformer",
    });
    const second = useScenarioDrafts.getState().createDraft({
      name: "Scenario 2",
      projectId: "project-1",
      graphId: "graph-1",
      baseVersion: 2,
      baseTitle: "Vision transformer",
    });

    useScenarioDrafts.getState().stagePatches(first.id, [makePatch("p1"), makePatch("p2")]);
    useScenarioDrafts.getState().removePatch(first.id, "p1");

    const state = useScenarioDrafts.getState();
    expect(state.drafts.find((draft) => draft.id === first.id)?.patches.map((patch) => patch.patch_id)).toEqual([
      "p2",
    ]);
    expect(state.drafts.find((draft) => draft.id === second.id)?.patches).toEqual([]);
  });

  it("deleting the active draft clears staging", () => {
    const draft = useScenarioDrafts.getState().createDraft({
      name: "Scenario 1",
      projectId: "project-1",
      graphId: "graph-1",
      baseVersion: 2,
      baseTitle: "Vision transformer",
    });

    useScenarioDrafts.getState().deleteDraft(draft.id);

    const state = useScenarioDrafts.getState();
    expect(state.drafts).toEqual([]);
    expect(state.activeDraftId).toBeNull();
  });

  it("resolves the active draft only for its own graph", () => {
    const draft = useScenarioDrafts.getState().createDraft({
      name: "Scenario 1",
      projectId: "project-1",
      graphId: "graph-1",
      baseVersion: 2,
      baseTitle: "Vision transformer",
    });

    const state = useScenarioDrafts.getState();
    expect(activeDraftForGraph(state, "project-1", "graph-1")?.id).toBe(draft.id);
    expect(activeDraftForGraph(state, "project-1", "graph-2")).toBeNull();

    useScenarioDrafts.getState().setActiveDraft(null);
    expect(
      activeDraftForGraph(useScenarioDrafts.getState(), "project-1", "graph-1"),
    ).toBeNull();
  });
});
