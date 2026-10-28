import { describe, expect, it } from "vitest";
import type { GraphNode, MethodologyGraph } from "../../lib/types.ts";
import {
  acceptNodePatch,
  buildCorrectionBatch,
  editNodePatch,
  rejectNodePatches,
  stripAssumptionKeys,
} from "./correctionPatches.ts";

/** Clearly-marked fake: one extracted component for patch tests. */
function fakeNode(id: string, config: Record<string, unknown> = {}): GraphNode {
  return {
    id,
    kind: "component",
    label: `Fake ${id}`,
    description: `Fake description of ${id}.`,
    config,
    input_shape: null,
    output_shape: null,
    evidence: [],
    provenance: "unresolved",
    confidence: 0.4,
  };
}

/** Clearly-marked fake: two connected components under review. */
const fakeGraph: MethodologyGraph = {
  schema_version: "1.0",
  project_id: "fake-project",
  graph_id: "fake-graph",
  version: 1,
  title: "Fake methodology",
  source_ids: ["fake-paper"],
  nodes: [
    fakeNode("fake-a", { assumed: true, assumption_reason: "Fake reason.", kept: "yes" }),
    fakeNode("fake-b"),
  ],
  edges: [
    {
      id: "fake-e1",
      source: "fake-a",
      target: "fake-b",
      relation: "data_flow",
      label: null,
      evidence: [],
      provenance: "extracted",
    },
  ],
  created_by: "fake-user",
  parent_version: null,
};

describe("correction patch builders", () => {
  it("builds an accept patch that clears the assumed marking", () => {
    const patch = acceptNodePatch(fakeGraph, fakeGraph.nodes[0]);
    expect(patch).toMatchObject({
      base_graph_id: "fake-graph",
      base_version: 1,
      operation: "replace_node",
      target_id: "fake-a",
      requested_by: "correction-ui",
    });
    expect(patch.patch_id).toMatch(/^correction-/);
    expect(patch.payload["node"]).toMatchObject({
      id: "fake-a",
      kind: "component",
      label: "Fake fake-a",
      config: { kept: "yes" },
      provenance: "verified",
      confidence: 0.4,
    });
    expect(patch.rationale).toContain("fake-a");
  });

  it("builds an edit patch with corrected fields and verified provenance", () => {
    const patch = editNodePatch(fakeGraph, fakeGraph.nodes[1], {
      label: "Fake corrected",
      description: "Fake reviewer correction.",
      config: { layers: 4, assumed: true },
    });
    expect(patch).toMatchObject({ operation: "replace_node", target_id: "fake-b" });
    expect(patch.payload["node"]).toMatchObject({
      id: "fake-b",
      label: "Fake corrected",
      description: "Fake reviewer correction.",
      config: { layers: 4 },
      provenance: "verified",
    });
  });

  it("rejects an edit with a blank label", () => {
    expect(() =>
      editNodePatch(fakeGraph, fakeGraph.nodes[0], {
        label: "  ",
        description: null,
        config: {},
      }),
    ).toThrow("label is required");
  });

  it("orders reject patches edges-first with connected edges included", () => {
    const patches = rejectNodePatches(fakeGraph, fakeGraph.nodes[0]);
    expect(patches.map((patch) => patch.operation)).toEqual([
      "remove_edge",
      "remove_node",
    ]);
    expect(patches[0].target_id).toBe("fake-e1");
    expect(patches[1].target_id).toBe("fake-a");
  });

  it("builds a mixed batch as one atomic unit with uniform base", () => {
    const patches = buildCorrectionBatch(fakeGraph, [
      { nodeId: "fake-a", action: "accept" },
      {
        nodeId: "fake-b",
        action: "edit",
        edit: { label: "Fake corrected", description: null, config: {} },
      },
    ]);
    expect(patches).toHaveLength(2);
    for (const patch of patches) {
      expect(patch.base_version).toBe(1);
      expect(patch.requested_by).toBe("correction-ui");
    }
  });

  it("sorts batch removals edges-first across decisions", () => {
    const patches = buildCorrectionBatch(fakeGraph, [
      { nodeId: "fake-a", action: "reject" },
      { nodeId: "fake-b", action: "accept" },
    ]);
    expect(patches.map((patch) => patch.operation)).toEqual([
      "remove_edge",
      "remove_node",
      "replace_node",
    ]);
  });

  it("rejects unknown nodes and missing edit payloads", () => {
    expect(() =>
      buildCorrectionBatch(fakeGraph, [{ nodeId: "fake-missing", action: "accept" }]),
    ).toThrow("fake-missing");
    expect(() =>
      buildCorrectionBatch(fakeGraph, [{ nodeId: "fake-a", action: "edit" }]),
    ).toThrow("Missing edit payload");
  });

  it("strips only the assumption keys from a config", () => {
    expect(
      stripAssumptionKeys({ assumed: true, assumption_reason: "x", kept: 1 }),
    ).toEqual({ kept: 1 });
  });
});
