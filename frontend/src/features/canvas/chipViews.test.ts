import { describe, expect, it } from "vitest";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import {
  arrayDimensions,
  chipScope,
  connectedScope,
  floorplanLayout,
  schematicBoxes,
  schematicSupport,
} from "./chipViews.ts";

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

  it("hides non-physical nodes even inside the electronics domain", () => {
    const mixed: GraphEntities = {
      ...entitiesFixture,
      entities: entitiesFixture.entities.map((entity) =>
        entity.node_id === "encoder" ? { ...entity, physical: false, symbol: "dataset" } : entity,
      ),
    };
    const scope = chipScope(graphFixture, mixed);
    expect(scope.graph.nodes.map((node) => node.id)).toEqual(["input"]);
    expect(scope.hiddenCount).toBe(1);
  });

  it("hides everything when entities are unavailable", () => {
    const scope = chipScope(graphFixture, null);
    expect(scope.graph.nodes).toEqual([]);
    expect(scope.hiddenCount).toBe(2);
  });
});

describe("arrayDimensions", () => {
  function graphWithConfigs(configs: Record<string, Record<string, unknown>>): MethodologyGraph {
    return {
      ...graphFixture,
      nodes: graphFixture.nodes.map((node) => ({ ...node, config: configs[node.id] ?? {} })),
      edges: [],
    };
  }

  it("reads explicit array geometry from node config", () => {
    const dims = arrayDimensions(
      chipScope(graphWithConfigs({ input: { array: "16x16" } }), entitiesFixture),
    );
    expect(dims).toMatchObject({ rows: 16, columns: 16, sourceNodeId: "input" });
  });

  it("accepts row/column count pairs and rejects junk", () => {
    const pairs = arrayDimensions(
      chipScope(
        graphWithConfigs({ input: { column_units: 16, cells_per_column: 16 } }),
        entitiesFixture,
      ),
    );
    expect(pairs).toMatchObject({ rows: 16, columns: 16 });
    const junk = arrayDimensions(
      chipScope(graphWithConfigs({ input: { array: "large" } }), entitiesFixture),
    );
    expect(junk).toBeNull();
  });

  it("finds explicit dimensions in node text as a fallback", () => {
    const graph = {
      ...graphFixture,
      nodes: graphFixture.nodes.map((node) =>
        node.id === "input"
          ? { ...node, description: "chips each with 8x32 array (256 bits)" }
          : node,
      ),
      edges: [],
    };
    expect(arrayDimensions(chipScope(graph, entitiesFixture))).toMatchObject({
      rows: 8,
      columns: 32,
    });
  });

  it("returns null when no dimensions are stated", () => {
    expect(arrayDimensions(chipScope(graphFixture, entitiesFixture))).toBeNull();
  });
});

describe("schematicSupport", () => {
  it("requires connected electronics parts with at least one edge", () => {
    expect(schematicSupport(chipScope(graphFixture, entitiesFixture))).toBe(true);
    const edgeless = { ...graphFixture, edges: [] };
    expect(schematicSupport(chipScope(edgeless, entitiesFixture))).toBe(false);
    expect(schematicSupport(chipScope(graphFixture, processEntities))).toBe(false);
  });

  it("keeps only connected parts and counts the dropped rest", () => {
    const graph = {
      ...graphFixture,
      nodes: [
        ...graphFixture.nodes,
        { ...graphFixture.nodes[0], id: "lonely", label: "Lonely part" },
      ],
    };
    const entities: GraphEntities = {
      ...entitiesFixture,
      entities: [
        ...entitiesFixture.entities,
        { ...entitiesFixture.entities[0], node_id: "lonely" },
      ],
    };
    const { scope, droppedCount } = connectedScope(chipScope(graph, entities));
    expect(scope.graph.nodes.map((node) => node.id).sort()).toEqual(["encoder", "input"]);
    expect(droppedCount).toBe(1);
  });
});

describe("schematicBoxes", () => {
  it("expands bitcells and compacts every other symbol", () => {
    const { boxes, width, height } = schematicBoxes(chipScope(graphFixture, entitiesFixture));
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toMatchObject({ nodeId: "input", symbol: "bitcell", expanded: true });
    expect(boxes[0].w).toBeGreaterThan(boxes[0].h);
    expect(boxes[1]).toMatchObject({ nodeId: "encoder", symbol: "generic", expanded: false });
    // Every box sits fully inside the sheet: no negative origins.
    for (const box of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(24);
      expect(box.y).toBeGreaterThanOrEqual(24);
      expect(box.x + box.w).toBeLessThanOrEqual(width);
      expect(box.y + box.h).toBeLessThanOrEqual(height);
    }
  });

  it("keeps small schematics at a readable minimum sheet size", () => {
    const { width, height } = schematicBoxes(chipScope(graphFixture, entitiesFixture));
    expect(width).toBeGreaterThanOrEqual(640);
    expect(height).toBeGreaterThanOrEqual(400);
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

  function dims(rows: number, columns: number) {
    return { rows, columns, sourceNodeId: "block-0", source: "config" as const };
  }

  it("lays the stated array geometry with periphery blocks below", () => {
    const graph = graphWith(2, 2);
    const layout = floorplanLayout(chipScope(graph, entitiesFor(graph)), dims(4, 8));
    expect(layout.columns).toBe(8);
    expect(layout.rows).toBe(4);
    expect(layout.downsampled).toBe(false);
    expect(layout.items.filter((item) => item.kind === "cell")).toHaveLength(32);
    const blocks = layout.items.filter((item) => item.kind === "block");
    expect(blocks).toHaveLength(2);
    const lowestCell = Math.max(...layout.items.filter((i) => i.kind === "cell").map((i) => i.y + i.h));
    for (const block of blocks) expect(block.y).toBeGreaterThanOrEqual(lowestCell);
  });

  it("links every cell to the bitcell node, or the dims source", () => {
    const graph = graphWith(2, 1);
    const layout = floorplanLayout(chipScope(graph, entitiesFor(graph)), dims(2, 2));
    const cells = layout.items.filter((item) => item.kind === "cell");
    expect(new Set(cells.map((cell) => cell.nodeId))).toEqual(new Set(["cell-0"]));
    const noBitcells = floorplanLayout(
      chipScope(graphWith(0, 1), entitiesFor(graphWith(0, 1))),
      dims(2, 2),
    );
    expect(noBitcells.items.filter((i) => i.kind === "cell")[0]?.nodeId).toBe("block-0");
  });

  it("downsamples huge arrays while preserving aspect", () => {
    const graph = graphWith(1, 0);
    const layout = floorplanLayout(chipScope(graph, entitiesFor(graph)), dims(512, 128));
    expect(layout.downsampled).toBe(true);
    expect(layout.rows / layout.columns).toBeCloseTo(4, 0);
    expect(layout.items.filter((item) => item.kind === "cell").length).toBeLessThanOrEqual(2500);
  });

  it("keeps small floorplans at a readable minimum sheet size", () => {
    const graph = graphWith(1, 1);
    const layout = floorplanLayout(chipScope(graph, entitiesFor(graph)), dims(2, 2));
    expect(layout.width).toBeGreaterThanOrEqual(560);
    expect(layout.height).toBeGreaterThanOrEqual(360);
  });
});
