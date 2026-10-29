import { describe, expect, it } from "vitest";
import type { EntityResolution, GraphEntities } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import {
  KIND_COLORS,
  archetypeFor,
  boundingSphere,
  categoryLabel,
  domainLabel,
  fitDistance,
  isStructural,
  legendEntries,
  prettyEntityType,
  resolutionsByNodeId,
  splitGraph,
  symbolLabel,
  toWorldPositions,
  visualFor,
} from "./graph3d.ts";

function resolution(overrides: Partial<EntityResolution>): EntityResolution {
  return {
    node_id: "n1",
    domain: "electronics",
    entity_type: "memory-cell",
    display_label: "Memory cell",
    generic: false,
    category: "package",
    physical: true,
    symbol: "bitcell",
    model_3d: null,
    interfaces: [],
    matched_terms: [],
    confidence: 1,
    ...overrides,
  };
}

describe("3D world mapping", () => {
  it("lifts the 2D floor plan into a depth cascade", () => {
    const positions = toWorldPositions(graphFixture, null);
    // Fixture: input (layer 0) -> encoder (layer 1); auto-layout pitches
    // 280px horizontal and 170px vertical, plus the depth helix.
    expect(positions.get("input")).toEqual({ x: 0, y: 0, z: 0 });
    const encoder = positions.get("encoder");
    expect(encoder?.x).toBeCloseTo(Math.sin(0.65) * 6, 5);
    expect(encoder?.y).toBeCloseTo(3.2, 5);
    expect(encoder?.z).toBeCloseTo((Math.cos(0.65) - 1) * 6, 5);
  });

  it("colors every node kind with a muted earth tone", () => {
    expect(Object.keys(KIND_COLORS).sort()).toEqual(
      [
        "component",
        "dataset",
        "evaluation",
        "input",
        "loss",
        "model",
        "operation",
        "optimizer",
        "output",
        "preprocessing",
      ].sort(),
    );
    for (const color of Object.values(KIND_COLORS)) {
      expect(Number.isInteger(color)).toBe(true);
    }
  });

  it("bounds nodes in a sphere for camera fitting", () => {
    const positions = toWorldPositions(graphFixture, null);
    const points = [...positions.values()];
    const { center, radius } = boundingSphere(positions);
    expect(center.x).toBeCloseTo((points[0].x + points[1].x) / 2, 5);
    expect(center.y).toBeCloseTo((points[0].y + points[1].y) / 2, 5);
    expect(center.z).toBeCloseTo((points[0].z + points[1].z) / 2, 5);
    expect(radius).toBeGreaterThan(0);
    expect(boundingSphere(new Map()).radius).toBe(1);
  });

  it("fits the rotation-invariant ring so orbiting never clips", () => {
    const positions = new Map([
      ["a", { x: -4, y: 0, z: 0 }],
      ["b", { x: 4, y: 0, z: 0 }],
    ]);
    // The segment sweeps a ring of radius 4; the near ring corner dominates.
    const headOn = fitDistance(positions, { x: 0, y: 0, z: 1 }, 45, 1, 0, 1);
    expect(headOn).toBeCloseTo(4 / Math.tan((22.5 * Math.PI) / 180) + 4, 5);
    // Diagonal views need strictly more room than a flat head-on fit.
    const diagonal = fitDistance(positions, { x: 1, y: 0.85, z: 1 }, 45, 16 / 9, 1.1, 1);
    expect(diagonal).toBeGreaterThan(4 / Math.tan((22.5 * Math.PI) / 180));
    expect(fitDistance(new Map(), { x: 0, y: 0, z: 1 }, 45, 1)).toBe(10);
  });
});

describe("library category glyphs", () => {
  it("maps each category to a distinct primitive within a domain", () => {
    // Electronics set: every category renders a different shape.
    const electronics = ["package", "discrete", "power", "sensor", "passive"].map(archetypeFor);
    expect(new Set(electronics).size).toBe(electronics.length);
    // Deep-learning set, including the flattened layer slab.
    expect(archetypeFor("layer")).toBe("slab");
    expect(archetypeFor("storage")).toBe("cylinder");
    expect(archetypeFor("service")).toBe("dodecahedron");
  });

  it("falls back to the sphere for unknown or missing categories", () => {
    expect(archetypeFor("quantum-foam")).toBe("sphere");
    expect(archetypeFor(null)).toBe("sphere");
    expect(archetypeFor(undefined)).toBe("sphere");
    expect(categoryLabel("quantum-foam")).toBe("Generic");
    expect(categoryLabel("process")).toBe("Process");
    expect(domainLabel("astrophysics")).toBe("Generic");
  });
});

describe("render-spec visuals", () => {
  it("derives 3D shapes from the pack-declared symbol, never the category", () => {
    // Same coarse category, different entities: the symbol decides.
    expect(visualFor(resolution({ symbol: "bitcell", category: "package" }))).toBe("box");
    expect(visualFor(resolution({ symbol: "chip", category: "package" }))).toBe("box");
    expect(visualFor(resolution({ symbol: "attention", category: "layer" }))).toBe("slab");
    expect(visualFor(resolution({ symbol: "transistor", category: "discrete" }))).toBe("cone");
    // A misleading category cannot smuggle in a hardware shape.
    expect(visualFor(resolution({ symbol: "dataset", category: "sensor" }))).toBe("cylinder");
  });

  it("lets an explicit model_3d key override the symbol visual", () => {
    expect(visualFor(resolution({ symbol: "bitcell", model_3d: "cylinder" }))).toBe("cylinder");
    // Unknown model keys fall back to the neutral sphere, never crash.
    expect(visualFor(resolution({ symbol: "bitcell", model_3d: "quantum-foam" }))).toBe(
      "sphere",
    );
  });

  it("renders unknown, generic, and missing resolutions as neutral spheres", () => {
    expect(visualFor(resolution({ symbol: "quantum-foam" }))).toBe("sphere");
    expect(visualFor(resolution({ generic: true, symbol: "generic" }))).toBe("sphere");
    expect(visualFor(null)).toBe("sphere");
    expect(visualFor(undefined)).toBe("sphere");
  });

  it("labels symbols with curated names and a kebab-case fallback", () => {
    expect(symbolLabel("senseamp")).toBe("Sense amplifier");
    expect(symbolLabel("adc")).toBe("Data converter");
    expect(symbolLabel("mcu")).toBe("Microcontroller");
    expect(symbolLabel("bitcell")).toBe("Bitcell");
    expect(symbolLabel("quantum-foam")).toBe("Quantum Foam");
  });

  it("groups resolutions into legend entries by symbol", () => {
    const entries = legendEntries(entitiesFixture);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({
      symbol: "bitcell",
      label: "Bitcell",
      geometry: "box",
      count: 1,
      entityTypes: ["Memory Cell"],
    });
    expect(entries[1]).toMatchObject({
      symbol: "generic",
      label: "Generic",
      geometry: "sphere",
      count: 1,
    });
    expect(legendEntries(null)).toEqual([]);
  });

  it("prettifies entity type ids and indexes resolutions by node", () => {
    expect(prettyEntityType("memory-cell")).toBe("Memory Cell");
    const index = resolutionsByNodeId(entitiesFixture);
    expect(index.get("input")?.entity_type).toBe("memory-cell");
    expect(index.get("encoder")?.generic).toBe(true);
    expect(resolutionsByNodeId(null).size).toBe(0);
  });
});

describe("structure/process split", () => {
  function entitiesFor(flags: Record<string, boolean>): GraphEntities {
    return {
      ...entitiesFixture,
      entities: graphFixture.nodes.map((node) => {
        const base = entitiesFixture.entities.find((entity) => entity.node_id === node.id);
        const physical = flags[node.id] ?? true;
        if (base) return { ...base, physical };
        return resolution({ node_id: node.id, physical });
      }),
    };
  }

  it("treats unresolved and unflagged nodes as structure", () => {
    expect(isStructural(null)).toBe(true);
    expect(isStructural(undefined)).toBe(true);
    expect(isStructural(resolution({ physical: true }))).toBe(true);
    expect(isStructural(resolution({ physical: false }))).toBe(false);
    // Stale payloads without the flag stay structural instead of vanishing.
    expect(isStructural({ physical: undefined } as unknown as EntityResolution)).toBe(true);
  });

  it("splits nodes by physicality and drops dangling edges", () => {
    const split = splitGraph(graphFixture, entitiesFor({ input: true, encoder: false }));
    expect(split.structure.nodes.map((node) => node.id)).toEqual(["input"]);
    expect(split.process.nodes.map((node) => node.id)).toEqual(["encoder"]);
    // e1 spans the split, so neither side keeps it.
    expect(split.structure.edges).toEqual([]);
    expect(split.process.edges).toEqual([]);
    expect(split.structure.version).toBe(graphFixture.version);
    expect(split.process.title).toBe(graphFixture.title);
  });

  it("keeps internal edges on each side of the split", () => {
    const split = splitGraph(graphFixture, entitiesFor({}));
    expect(split.structure.nodes).toHaveLength(2);
    expect(split.structure.edges.map((edge) => edge.id)).toEqual(["e1"]);
    expect(split.process.nodes).toEqual([]);
  });

  it("keeps every node structural when entities are unavailable", () => {
    const split = splitGraph(graphFixture, null);
    expect(split.structure.nodes).toHaveLength(2);
    expect(split.process.nodes).toEqual([]);
  });
});
