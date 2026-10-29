import { describe, expect, it } from "vitest";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import { chipScope, floorplanLayout, schematicBoxes } from "./chipViews.ts";

const processEntities: GraphEntities = {
  ...entitiesFixture,
  classification: { domain: "deep-learning", confidence: 0.9, signals: ["training"] },
  entities: [
    {
      node_id: "input",
      domain: "deep-learning",
      entity_type: "dataloader",
      display_label: "Training data",
      generic: false,
      category: "process",
      physical: false,
      symbol: "dataset",
      model_3d: null,
      interfaces: [],
      matched_terms: [],
      confidence: 1,
    },
    {
      node_id: "encoder",
      domain: "deep-learning",
      entity_type: "attention-block",
      display_label: "Attention",
      generic: false,
      category: "layer",
      physical: true,
      symbol: "attention",
      model_3d: null,
      interfaces: [],
      matched_terms: ["attention"],
      confidence: 0.8,
    },
  ],
};

describe("chipScope", () => {
  it("keeps electronics-resolved nodes and counts the hidden rest", () => {
    const scope = chipScope(graphFixture, entitiesFixture);
    // Fixture: input resolves to memory-cell; the generic encoder stays
    // too, as a labeled placeholder rather than a guessed part.
    expect(scope.graph.nodes.map((node) => node.id)).toEqual(["input", "encoder"]);
    expect(scope.hiddenCount).toBe(0);
    expect(scope.resolutions.get("input")?.symbol).toBe("bitcell");
    expect(scope.resolutions.get("encoder")?.symbol).toBe("generic");
  });

  it("drops edges that leave the electronics scope", () => {
    const scope = chipScope(graphFixture, entitiesFixture);
    expect(scope.graph.edges.map((edge) => edge.id)).toEqual(["e1"]);
    const scoped = chipScope(graphFixture, processEntities);
    expect(scoped.graph.edges).toEqual([]);
  });

  it("hides everything when no node resolves to electronics", () => {
    const scope = chipScope(graphFixture, processEntities);
    expect(scope.graph.nodes).toEqual([]);
    expect(scope.hiddenCount).toBe(2);
  });

  it("hides everything when entities are unavailable", () => {
    const scope = chipScope(graphFixture, null);
    expect(scope.graph.nodes).toEqual([]);
    expect(scope.hiddenCount).toBe(2);
  });
});

describe("schematicBoxes", () => {
  it("expands bitcells and compacts every other symbol", () => {
    const { boxes, width, height } = schematicBoxes(chipScope(graphFixture, entitiesFixture));
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toMatchObject({ nodeId: "input", symbol: "bitcell", expanded: true });
    expect(boxes[0].w).toBeGreaterThan(boxes[0].h);
    expect(boxes[1]).toMatchObject({ nodeId: "encoder", symbol: "generic", expanded: false });
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
  });

  it("centers default boxes on the deterministic auto-layout", () => {
    const first = schematicBoxes(chipScope(graphFixture, entitiesFixture));
    const second = schematicBoxes(chipScope(graphFixture, entitiesFixture));
    expect(first).toEqual(second);
  });
});

describe("floorplanLayout", () => {
  function graphWith(cells: number, blocks: number): MethodologyGraph {
    const nodes = [
      ...Array.from({ length: cells }, (_, i) => ({
        ...graphFixture.nodes[0],
        id: `cell-${i}`,
        label: `Bitcell ${i}`,
      })),
      ...Array.from({ length: blocks }, (_, i) => ({
        ...graphFixture.nodes[0],
        id: `block-${i}`,
        label: `Sense amp ${i}`,
      })),
    ];
    return { ...graphFixture, nodes, edges: [] };
  }

  function entitiesFor(graph: MethodologyGraph): GraphEntities {
    return {
      ...entitiesFixture,
      entities: graph.nodes.map((node) => ({
        ...entitiesFixture.entities[0],
        node_id: node.id,
        symbol: node.id.startsWith("cell-") ? "bitcell" : "senseamp",
        entity_type: node.id.startsWith("cell-") ? "memory-cell" : "sense-amplifier",
      })),
    };
  }

  it("lays bitcells in a square-ish grid with periphery blocks below", () => {
    const graph = graphWith(5, 2);
    const layout = floorplanLayout(chipScope(graph, entitiesFor(graph)));
    expect(layout.columns).toBe(3);
    expect(layout.rows).toBe(2);
    expect(layout.items.filter((item) => item.kind === "cell")).toHaveLength(5);
    const blocks = layout.items.filter((item) => item.kind === "block");
    expect(blocks).toHaveLength(2);
    const lowestCell = Math.max(...layout.items.filter((i) => i.kind === "cell").map((i) => i.y + i.h));
    for (const block of blocks) expect(block.y).toBeGreaterThanOrEqual(lowestCell);
  });

  it("handles an array with no periphery and no array at all", () => {
    const cellsOnly = floorplanLayout(chipScope(graphWith(1, 0), entitiesFor(graphWith(1, 0))));
    expect(cellsOnly.columns).toBe(1);
    expect(cellsOnly.rows).toBe(1);
    const empty = floorplanLayout(chipScope(graphFixture, processEntities));
    expect(empty.items).toEqual([]);
    expect(empty.columns).toBe(0);
  });
});
