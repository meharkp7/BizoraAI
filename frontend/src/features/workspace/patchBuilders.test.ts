import { describe, expect, it } from "vitest";
import { graphFixture } from "../../test/fixtures.ts";
import {
  addEdgePatch,
  addNodePatch,
  nodeIdProblem,
  removalBatch,
  replaceNodePatch,
  suggestNodeId,
  updateConfigPatch,
} from "./patchBuilders.ts";

describe("patch builders", () => {
  it("builds an add-node patch against the viewed revision", () => {
    const patch = addNodePatch(graphFixture, { id: "head", kind: "output", label: "Head" });
    expect(patch).toMatchObject({
      base_graph_id: "graph-1",
      base_version: 2,
      operation: "add_node",
      target_id: null,
      requested_by: "workspace-ui",
    });
    expect(patch.payload["node"]).toMatchObject({ id: "head", kind: "output" });
    expect(patch.patch_id).toMatch(/^canvas-/);
  });

  it("builds an add-edge patch", () => {
    const patch = addEdgePatch(graphFixture, "e9", "input", "encoder");
    expect(patch).toMatchObject({ operation: "add_edge", target_id: null });
    expect(patch.payload["edge"]).toMatchObject({
      id: "e9",
      source: "input",
      target: "encoder",
    });
  });

  it("builds a replace-node patch retaining the id", () => {
    const patch = replaceNodePatch(graphFixture, graphFixture.nodes[1], {
      kind: "operation",
      label: "INT8 quantizer",
      description: "Replacement quantizer",
      config: { bits: 8 },
    });
    expect(patch).toMatchObject({
      operation: "replace_node",
      target_id: "encoder",
      requested_by: "workspace-ui",
    });
    expect(patch.payload["node"]).toMatchObject({
      id: "encoder",
      kind: "operation",
      label: "INT8 quantizer",
      description: "Replacement quantizer",
      config: { bits: 8 },
    });
    expect(patch.rationale).toContain("encoder");
  });

  it("builds an update-config patch", () => {
    const patch = updateConfigPatch(graphFixture, graphFixture.nodes[1], { layers: 24 });
    expect(patch).toMatchObject({
      operation: "update_node_config",
      target_id: "encoder",
    });
    expect(patch.payload).toEqual({ config: { layers: 24 } });
  });

  it("orders removals edges-first with connected edges included", () => {
    const patches = removalBatch(graphFixture, ["encoder"], []);
    expect(patches.map((patch) => patch.operation)).toEqual(["remove_edge", "remove_node"]);
    expect(patches[0].target_id).toBe("e1");
    expect(patches[1].target_id).toBe("encoder");
  });

  it("dedupes explicitly selected edges of removed nodes", () => {
    const patches = removalBatch(graphFixture, ["encoder"], ["e1"]);
    expect(patches).toHaveLength(2);
  });

  it("removes lone edges without touching nodes", () => {
    const patches = removalBatch(graphFixture, [], ["e1"]);
    expect(patches).toHaveLength(1);
    expect(patches[0]).toMatchObject({ operation: "remove_edge", target_id: "e1" });
  });

  it("carries catalog description and config on an add-node patch", () => {
    const patch = addNodePatch(
      graphFixture,
      { id: "q1", kind: "component", label: "2N3904" },
      { description: "NPN transistor", config: { part: "2N3904" } },
    );
    expect(patch.payload["node"]).toMatchObject({
      id: "q1",
      kind: "component",
      label: "2N3904",
      description: "NPN transistor",
      config: { part: "2N3904" },
    });
  });

  it("suggests a unique slug id from a label", () => {
    expect(suggestNodeId(graphFixture, "2N3904 NPN transistor")).toBe("2n3904-npn-transistor");
    expect(suggestNodeId(graphFixture, "Transformer encoder")).toBe("transformer-encoder");
    expect(suggestNodeId(graphFixture, "input")).toBe("input-2");
    expect(suggestNodeId(graphFixture, "!!!")).toBe("node");
  });

  it("explains unusable node ids", () => {
    expect(nodeIdProblem(graphFixture, "q1")).toBeNull();
    expect(nodeIdProblem(graphFixture, "input")).toBe("This ID is already in the graph.");
    expect(nodeIdProblem(graphFixture, "-bad")).toContain("start with a letter or digit");
    expect(nodeIdProblem(graphFixture, "")).toContain("start with a letter or digit");
  });
});
