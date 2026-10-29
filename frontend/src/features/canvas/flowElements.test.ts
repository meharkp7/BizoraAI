import { describe, expect, it } from "vitest";
import type { MeasuredOverlay } from "../../lib/types.ts";
import { diffFixture, graphFixture, layoutFixture } from "../../test/fixtures.ts";
import { diffStatusMaps, measuredSummary, toFlowElements } from "./flowElements.ts";
import type { CanvasDiffStatuses } from "./flowElements.ts";

function statuses(): CanvasDiffStatuses {
  return {
    nodes: new Map(diffFixture.changed_nodes.map((change) => [change.node_id, "changed" as const])),
    edges: new Map(),
  };
}

describe("diffStatusMaps", () => {
  it("maps added and changed elements, skipping removed ones", () => {
    const statuses = diffStatusMaps({
      ...diffFixture,
      added_nodes: [graphFixture.nodes[0]],
      removed_nodes: [graphFixture.nodes[1]],
    });
    expect(statuses.nodes.get("input")).toBe("added");
    expect(statuses.nodes.get("encoder")).toBe("changed");
    expect(statuses.edges.size).toBe(0);
  });
});

describe("toFlowElements", () => {
  it("maps nodes with saved positions and selection flags", () => {
    const { nodes, edges } = toFlowElements(graphFixture, layoutFixture, null, ["encoder"], []);
    expect(nodes).toHaveLength(2);
    const input = nodes.find((node) => node.id === "input");
    const encoder = nodes.find((node) => node.id === "encoder");
    expect(input?.position).toEqual({ x: 10, y: 20 });
    expect(input?.selected).toBe(false);
    expect(encoder?.selected).toBe(true);
    expect(encoder?.data).toMatchObject({ label: "Transformer encoder", kind: "model" });
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({ id: "e1", source: "input", target: "encoder" });
    expect(edges[0].data).toMatchObject({ relation: "data_flow" });
  });

  it("marks edge selection and diff statuses", () => {
    const { nodes, edges } = toFlowElements(graphFixture, null, statuses(), [], ["e1"]);
    expect(edges[0].selected).toBe(true);
    expect(nodes.find((node) => node.id === "encoder")?.data.diffStatus).toBe("changed");
    expect(nodes.find((node) => node.id === "input")?.data.diffStatus).toBeNull();
  });

  it("reveals a truncated label only on the selected edge", () => {
    const long = "reconstruction observed binary observations estimate dominant value";
    const graph = {
      ...graphFixture,
      edges: [{ ...graphFixture.edges[0], label: long }],
    };
    const hidden = toFlowElements(graph, null, null, [], []);
    expect(hidden.edges[0].label).toBeUndefined();
    const shown = toFlowElements(graph, null, null, [], ["e1"]);
    expect(shown.edges[0].label).toBe("reconstruction observed binary observat…");
  });

  it("falls back to auto-layout without a saved layout", () => {
    const { nodes } = toFlowElements(graphFixture, null, null, [], []);
    const byId = new Map(nodes.map((node) => [node.id, node.position]));
    expect(byId.get("input")).toEqual({ x: 0, y: 0 });
    expect(byId.get("encoder")).toEqual({ x: 0, y: 170 });
  });

  it("flags assumed nodes and defaults to unmeasured", () => {
    const graph = {
      ...graphFixture,
      nodes: graphFixture.nodes.map((node) =>
        node.id === "encoder" ? { ...node, config: { assumed: true } } : node,
      ),
    };
    const { nodes } = toFlowElements(graph, null, null, [], []);
    expect(nodes.find((node) => node.id === "encoder")?.data.assumed).toBe(true);
    expect(nodes.find((node) => node.id === "input")?.data.assumed).toBe(false);
    expect(nodes.find((node) => node.id === "input")?.data.measured).toEqual([]);
  });

  it("decorates nodes and edges from the measured overlay", () => {
    const overlay: MeasuredOverlay = {
      run_id: "run-1",
      nodes: { encoder: [{ signal: "acc", value: 0.91, unit: null }] },
      edges: { e1: [{ signal: "V", value: 1.2, unit: "V" }] },
    };
    const { nodes, edges } = toFlowElements(graphFixture, null, null, [], [], overlay);
    expect(nodes.find((node) => node.id === "encoder")?.data.measured).toEqual([
      { signal: "acc", value: 0.91, unit: null },
    ]);
    expect(edges[0].data?.measured).toEqual([{ signal: "V", value: 1.2, unit: "V" }]);
    expect(edges[0].label).toBe("V=1.2V");
  });

  it("summarizes overlay values for labels", () => {
    expect(measuredSummary([])).toBeUndefined();
    expect(measuredSummary([{ signal: "acc", value: 0.91, unit: null }])).toBe("acc=0.91");
    expect(
      measuredSummary([
        { signal: "V", value: 1.2, unit: "V" },
        { signal: "I", value: 3, unit: "mA" },
      ]),
    ).toBe("V=1.2V +1");
  });
});
