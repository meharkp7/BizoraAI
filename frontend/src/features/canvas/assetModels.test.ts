import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  buildProceduralGeometries,
  loadGlbModel,
  loadRequests,
  provenanceLabel,
  provenanceOf,
  specsByNodeId,
  summarizeProvenance,
} from "./assetModels.ts";
import type { NodeAssetSpec } from "./assetModels.ts";

function spec(overrides: Partial<NodeAssetSpec> & { nodeId: string }): NodeAssetSpec {
  return {
    label: overrides.nodeId,
    assetUri: null,
    fallbackPackage: null,
    illustrative: true,
    ...overrides,
  };
}

describe("asset provenance", () => {
  it("reads measured vs illustrative straight from the spec flag", () => {
    expect(provenanceOf(spec({ nodeId: "a", illustrative: false }))).toBe("measured");
    expect(provenanceOf(spec({ nodeId: "b", illustrative: true }))).toBe("illustrative");
    expect(provenanceLabel("measured")).toBe("Measured model");
    expect(provenanceLabel("illustrative")).toBe("Illustrative stand-in");
  });

  it("summarizes mixed specs for the explorer indicator", () => {
    const summary = summarizeProvenance([
      spec({ nodeId: "a", illustrative: false }),
      spec({ nodeId: "b", illustrative: false }),
      spec({ nodeId: "c", illustrative: true }),
    ]);
    expect(summary).toEqual({ measured: 2, illustrative: 1, total: 3 });
    expect(summarizeProvenance(null)).toEqual({ measured: 0, illustrative: 0, total: 0 });
    expect(summarizeProvenance([])).toEqual({ measured: 0, illustrative: 0, total: 0 });
  });

  it("indexes specs by node, first entry winning duplicates", () => {
    const index = specsByNodeId([
      spec({ nodeId: "a", label: "First" }),
      spec({ nodeId: "a", label: "Second" }),
    ]);
    expect(index.get("a")?.label).toBe("First");
    expect(specsByNodeId(null).size).toBe(0);
  });
});

describe("GLB load requests", () => {
  it("lists one fetch per node with a URI, skipping placeholders", () => {
    const requests = loadRequests([
      spec({ nodeId: "a", assetUri: "https://cdn.test/a.glb", illustrative: false }),
      spec({ nodeId: "b", assetUri: null }),
      spec({ nodeId: "c", assetUri: "" }),
      spec({ nodeId: "a", assetUri: "https://cdn.test/a-second.glb" }),
    ]);
    expect(requests).toEqual([{ nodeId: "a", url: "https://cdn.test/a.glb" }]);
    expect(loadRequests(null)).toEqual([]);
  });

  it("resolves the stub loader scene for the canvas swap-in", async () => {
    const group = new THREE.Group();
    group.name = "stub-model";
    const scene = await loadGlbModel("https://cdn.test/a.glb", {
      loadAsync: async (url: string) => {
        expect(url).toBe("https://cdn.test/a.glb");
        return { scene: group };
      },
    });
    expect(scene.name).toBe("stub-model");
  });

  it("propagates loader failures so the canvas keeps its placeholder", async () => {
    await expect(
      loadGlbModel("https://cdn.test/missing.glb", {
        loadAsync: async () => {
          throw new Error("404");
        },
      }),
    ).rejects.toThrow("404");
  });
});

describe("procedural fallback geometry", () => {
  const boxPart = {
    name: "body",
    vertices: [
      [-1, 0, -1],
      [1, 0, -1],
      [1, 2, -1],
      [-1, 2, -1],
      [-1, 0, 1],
      [1, 0, 1],
      [1, 2, 1],
      [-1, 2, 1],
    ] as [number, number, number][],
    faces: [
      [0, 1, 2],
      [0, 2, 3],
      [4, 6, 5],
      [4, 7, 6],
      [0, 4, 5],
      [0, 5, 1],
      [2, 6, 7],
      [2, 7, 3],
      [0, 3, 7],
      [0, 7, 4],
      [1, 5, 6],
      [1, 6, 2],
    ] as [number, number, number][],
  };

  it("builds one indexed BufferGeometry per part with normals", () => {
    const [geometry] = buildProceduralGeometries({ parts: [boxPart] });
    expect(geometry.getAttribute("position").count).toBe(8);
    expect(geometry.getIndex()?.count).toBe(36);
    expect(geometry.getAttribute("normal").count).toBe(8);
    geometry.computeBoundingBox();
    expect(geometry.boundingBox?.min.toArray()).toEqual([-1, 0, -1]);
    expect(geometry.boundingBox?.max.toArray()).toEqual([1, 2, 1]);
    geometry.dispose();
  });

  it("keeps every part separate for multi-solid fallbacks", () => {
    const pin = { ...boxPart, name: "pin-1" };
    const geometries = buildProceduralGeometries({ parts: [boxPart, pin] });
    expect(geometries).toHaveLength(2);
    for (const geometry of geometries) geometry.dispose();
  });
});
