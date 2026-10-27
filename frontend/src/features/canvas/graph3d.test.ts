import { describe, expect, it } from "vitest";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import {
  KIND_COLORS,
  archetypeFor,
  boundingSphere,
  categoryLabel,
  domainLabel,
  fitDistance,
  legendEntries,
  prettyEntityType,
  resolutionsByNodeId,
  toWorldPositions,
} from "./graph3d.ts";

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

describe("entity archetypes", () => {
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
    expect(domainLabel("astrophysics")).toBe("Generic");
  });

  it("groups resolutions into legend entries with generic kept separate", () => {
    const entries = legendEntries(entitiesFixture);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({
      category: "package",
      label: "Package",
      geometry: "box",
      count: 1,
      entityTypes: ["Memory Cell"],
    });
    expect(entries[1]).toMatchObject({
      category: "generic",
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
