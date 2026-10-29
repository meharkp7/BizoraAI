import { describe, expect, it } from "vitest";
import type { MethodologyGraph } from "../../lib/types.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { deriveFlowSteps } from "./flowSteps.ts";

function chainGraph(ids: string[]): MethodologyGraph {
  return {
    ...graphFixture,
    nodes: ids.map((id) => ({ ...graphFixture.nodes[0], id, label: `Step ${id}` })),
    edges: ids.slice(1).map((id, index) => ({
      ...graphFixture.edges[0],
      id: `e-${id}`,
      source: ids[index],
      target: id,
    })),
  };
}

describe("deriveFlowSteps", () => {
  it("orders a chain from sources to sinks", () => {
    const steps = deriveFlowSteps(chainGraph(["a", "b", "c"]));

    expect(steps.map((step) => step.nodeId)).toEqual(["a", "b", "c"]);
    expect(steps[0]).toMatchObject({ index: 0, prevIds: [], nextIds: ["b"] });
    expect(steps[1]).toMatchObject({ index: 1, prevIds: ["a"], nextIds: ["c"] });
    expect(steps[2]).toMatchObject({ index: 2, prevIds: ["b"], nextIds: [] });
  });

  it("orders branches deterministically by layer then id", () => {
    const graph: MethodologyGraph = {
      ...graphFixture,
      nodes: ["b", "a", "c"].map((id) => ({
        ...graphFixture.nodes[0],
        id,
        label: `Step ${id}`,
      })),
      edges: [
        { ...graphFixture.edges[0], id: "e1", source: "a", target: "b" },
        { ...graphFixture.edges[0], id: "e2", source: "a", target: "c" },
      ],
    };
    const steps = deriveFlowSteps(graph);

    expect(steps.map((step) => step.nodeId)).toEqual(["a", "b", "c"]);
  });

  it("keeps disconnected nodes as their own steps", () => {
    const graph: MethodologyGraph = {
      ...graphFixture,
      nodes: ["b", "a"].map((id) => ({
        ...graphFixture.nodes[0],
        id,
        label: `Step ${id}`,
      })),
      edges: [],
    };
    const steps = deriveFlowSteps(graph);

    expect(steps.map((step) => step.nodeId)).toEqual(["a", "b"]);
  });

  it("is deterministic regardless of input order", () => {
    const graph = chainGraph(["a", "b", "c", "d"]);
    const shuffled: MethodologyGraph = {
      ...graph,
      nodes: [...graph.nodes].reverse(),
      edges: [...graph.edges].reverse(),
    };
    const forward = deriveFlowSteps(graph);
    const backward = deriveFlowSteps(shuffled);

    expect(backward).toEqual(forward);
  });

  it("returns no steps for an empty graph", () => {
    expect(deriveFlowSteps({ ...graphFixture, nodes: [], edges: [] })).toEqual([]);
  });
});
