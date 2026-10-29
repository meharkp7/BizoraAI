import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { EntityResolution } from "../../lib/types.ts";
import { entitiesFixture, graphFixture } from "../../test/fixtures.ts";
import {
  buildProceduralGeometries,
  buildProceduralGroup,
  loadGlbModel,
  loadRequests,
  meshSpecs,
  partLegendEntries,
  partRole,
  provenanceLabel,
  provenanceOf,
  specsByNodeId,
  summarizeProvenance,
} from "./assetModels.ts";
import type { NodeAssetSpec } from "./assetModels.ts";
import { resolutionsByNodeId } from "./graph3d.ts";

function spec(overrides: Partial<NodeAssetSpec> & { node_id: string }): NodeAssetSpec {
  return {
    label: overrides.node_id,
    asset_uri: null,
    fallback_package: null,
    illustrative: true,
    mesh: null,
    ...overrides,
  };
}

describe("asset provenance", () => {
  it("reads measured vs illustrative straight from the spec flag", () => {
    expect(provenanceOf(spec({ node_id: "a", illustrative: false }))).toBe("measured");
    expect(provenanceOf(spec({ node_id: "b", illustrative: true }))).toBe("illustrative");
    expect(provenanceLabel("measured")).toBe("Measured model");
    expect(provenanceLabel("illustrative")).toBe("Illustrative stand-in");
  });

  it("summarizes mixed specs for the explorer indicator", () => {
    const summary = summarizeProvenance([
      spec({ node_id: "a", illustrative: false }),
      spec({ node_id: "b", illustrative: false }),
      spec({ node_id: "c", illustrative: true }),
    ]);
    expect(summary).toEqual({ measured: 2, illustrative: 1, total: 3 });
    expect(summarizeProvenance(null)).toEqual({ measured: 0, illustrative: 0, total: 0 });
    expect(summarizeProvenance([])).toEqual({ measured: 0, illustrative: 0, total: 0 });
  });

  it("indexes specs by node, first entry winning duplicates", () => {
    const index = specsByNodeId([
      spec({ node_id: "a", label: "First" }),
      spec({ node_id: "a", label: "Second" }),
    ]);
    expect(index.get("a")?.label).toBe("First");
    expect(specsByNodeId(null).size).toBe(0);
  });
});

describe("GLB load requests", () => {
  it("lists one fetch per node with a URI, skipping placeholders", () => {
    const requests = loadRequests([
      spec({ node_id: "a", asset_uri: "https://cdn.test/a.glb", illustrative: false }),
      spec({ node_id: "b", asset_uri: null }),
      spec({ node_id: "c", asset_uri: "" }),
      spec({ node_id: "a", asset_uri: "https://cdn.test/a-second.glb" }),
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

  it("lists only specs carrying generated meshes, deduplicated by node", () => {
    const mesh = { parts: [boxPart] };
    const listed = meshSpecs([
      spec({ node_id: "a", mesh }),
      spec({ node_id: "b" }),
      spec({ node_id: "a", mesh }),
    ]);
    expect(listed.map((entry) => entry.node_id)).toEqual(["a"]);
    expect(meshSpecs(null)).toEqual([]);
  });

  it("routes body vs leads to material roles by part name", () => {
    expect(partRole("body")).toBe("body");
    expect(partRole("pin-1")).toBe("lead");
    expect(partRole("pin-32")).toBe("lead");
  });

  it("routes assembly solids to dark vs metal roles", () => {
    for (const dark of ["body", "pcb", "flange", "housing", "header"]) {
      expect(partRole(dark)).toBe("body");
    }
    for (const metal of ["can", "usb", "lid", "shaft", "tab", "pin-1"]) {
      expect(partRole(metal)).toBe("lead");
    }
  });

  it("ignores merge suffixes when routing roles", () => {
    expect(partRole("pcb-2")).toBe("body");
    expect(partRole("header-3")).toBe("body");
    expect(partRole("pin-1-2")).toBe("lead");
  });

  it("assembles named child meshes under one group", () => {
    const pin = { ...boxPart, name: "pin-1" };
    const seen: string[] = [];
    const group = buildProceduralGroup({ parts: [boxPart, pin] }, (role) => {
      seen.push(role);
      return new THREE.MeshBasicMaterial();
    });
    expect(group.children.map((child) => child.name)).toEqual(["body", "pin-1"]);
    expect(seen).toEqual(["body", "lead"]);
    for (const child of group.children) {
      const mesh = child as THREE.Mesh;
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
    }
  });
});

describe("part legend", () => {
  const resolutions = resolutionsByNodeId(entitiesFixture);

  it("rows one modeled node with part, provenance, and entity type", () => {
    const rows = partLegendEntries(
      [spec({ node_id: "input", label: "6T bitcell", illustrative: false })],
      graphFixture.nodes,
      resolutions,
    );
    expect(rows).toEqual([
      {
        nodeId: "input",
        partLabel: "6T bitcell",
        nodeLabel: "Image",
        provenance: "measured",
        entityType: "Memory Cell",
      },
    ]);
  });

  it("dedupes specs and omits entity types for generic nodes", () => {
    const generic = new Map<string, EntityResolution>([
      ["input", { ...resolutions.get("input")!, generic: true }],
    ]);
    const rows = partLegendEntries(
      [
        spec({ node_id: "input", label: "Part A" }),
        spec({ node_id: "input", label: "Part B" }),
      ],
      graphFixture.nodes,
      generic,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ partLabel: "Part A", entityType: null });
  });

  it("falls back to the node id for unknown labels", () => {
    const rows = partLegendEntries([spec({ node_id: "ghost" })], graphFixture.nodes, resolutions);
    expect(rows[0]).toMatchObject({ nodeId: "ghost", nodeLabel: "ghost" });
    expect(partLegendEntries(null, graphFixture.nodes, resolutions)).toEqual([]);
  });
});
