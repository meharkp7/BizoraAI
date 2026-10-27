import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode, MethodologyGraph } from "../../lib/types.ts";
import { autoLayout, layerByNodeId, matchesSavedPositions, resolvePositions } from "./layout.ts";

function node(id: string): GraphNode {
  return {
    id,
    kind: "model",
    label: id,
    description: null,
    config: {},
    input_shape: null,
    output_shape: null,
    evidence: [],
    provenance: "unresolved",
    confidence: null,
  };
}

function edge(id: string, source: string, target: string): GraphEdge {
  return {
    id,
    source,
    target,
    relation: "data_flow",
    label: null,
    evidence: [],
    provenance: "unresolved",
  };
}

function graph(nodes: string[], edges: [string, string, string][]): MethodologyGraph {
  return {
    schema_version: "1.0",
    project_id: "p",
    graph_id: "g",
    version: 1,
    title: "t",
    source_ids: [],
    nodes: nodes.map(node),
    edges: edges.map(([id, s, t]) => edge(id, s, t)),
    created_by: "test",
    parent_version: null,
  };
}

describe("layered auto-layout", () => {
  it("layers a chain downward in id order", () => {
    const layers = layerByNodeId(graph(["a", "b", "c"], [["e1", "a", "b"], ["e2", "b", "c"]]));
    expect([...layers.entries()].sort()).toEqual([
      ["a", 0],
      ["b", 1],
      ["c", 2],
    ]);
    const positions = autoLayout(graph(["a", "b"], [["e1", "a", "b"]]));
    expect(positions.get("a")).toEqual({ x: 0, y: 0 });
    expect(positions.get("b")).toEqual({ x: 0, y: 170 });
  });

  it("orders siblings by id and terminates on cycles", () => {
    const layers = layerByNodeId(
      graph(["b", "a"], [["e1", "a", "b"], ["e2", "b", "a"]]),
    );
    expect(layers.get("a")).toBe(0);
    expect(layers.has("b")).toBe(true);
    const positions = autoLayout(graph(["b", "a"], []));
    expect(positions.get("a")).toEqual({ x: 0, y: 0 });
    expect(positions.get("b")).toEqual({ x: 230, y: 0 });
  });

  it("detects position drift against saved layouts", () => {
    const saved = [{ node_id: "a", x: 50, y: 60, z: 0 }];
    expect(matchesSavedPositions(saved, new Map([["a", { x: 50, y: 60 }]]))).toBe(true);
    expect(matchesSavedPositions(saved, new Map([["a", { x: 51, y: 60 }]]))).toBe(false);
    expect(matchesSavedPositions(saved, new Map())).toBe(false);
  });

  it("prefers saved positions and fills gaps from auto-layout", () => {
    const g = graph(["a", "b"], [["e1", "a", "b"]]);
    const resolved = resolvePositions(g, {
      project_id: "p",
      graph_id: "g",
      version: 1,
      positions: [{ node_id: "a", x: 50, y: 60, z: 0 }],
      viewport: null,
      camera: null,
      updated_by: "test",
    });
    expect(resolved.get("a")).toEqual({ x: 50, y: 60 });
    expect(resolved.get("b")).toEqual({ x: 0, y: 170 });
  });
});
