import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { FigureSegment } from "../../lib/types.ts";
import {
  SEGMENT_MATCH_SIMILARITY,
  buildSegmentModel,
  labelSimilarity,
  matchSegmentToBlock,
  tracedColorForBlock,
} from "./segmentModels.ts";

function makeSegment(label: string): FigureSegment {
  return {
    segment_id: "seg-1",
    label,
    bbox: [0.1, 0.2, 0.3, 0.4],
    polygon: [
      [0.1, 0.2],
      [0.4, 0.2],
      [0.4, 0.6],
      [0.1, 0.6],
    ],
    score: 0.9,
  };
}

describe("labelSimilarity", () => {
  it("scores identical labels at 1 and disjoint labels at 0", () => {
    expect(labelSimilarity("nmos transistor", "nmos transistor")).toBe(1);
    expect(labelSimilarity("nmos transistor", "filter capacitor")).toBe(0);
    expect(labelSimilarity("", "nmos")).toBe(0);
  });

  it("matches partial restatements above the threshold", () => {
    expect(labelSimilarity("nmos", "nmos transistor")).toBeGreaterThanOrEqual(
      SEGMENT_MATCH_SIMILARITY,
    );
    expect(labelSimilarity("tilt comparator", "comparator")).toBeGreaterThanOrEqual(
      SEGMENT_MATCH_SIMILARITY,
    );
  });
});

describe("matchSegmentToBlock", () => {
  it("picks the best segment above threshold", () => {
    const segments = [makeSegment("filter capacitor"), makeSegment("nmos transistor")];
    expect(
      matchSegmentToBlock({ label: "nmos transistor switch" }, segments)?.label,
    ).toBe("nmos transistor");
  });

  it("matches instance names through their part family", () => {
    const segments = [makeSegment("nmos transistor")];
    expect(
      matchSegmentToBlock({ label: "N1", part: "nmos" }, segments)?.label,
    ).toBe("nmos transistor");
  });

  it("returns null when nothing is close", () => {
    expect(
      matchSegmentToBlock({ label: "voltage rail" }, [makeSegment("nmos transistor")]),
    ).toBeNull();
  });
});

describe("tracedColorForBlock", () => {
  it("tints by part family and falls back to bronze", () => {
    expect(tracedColorForBlock("nmos")).toBe(tracedColorForBlock("pmos"));
    expect(tracedColorForBlock("nmos")).not.toBe(tracedColorForBlock("capacitor"));
    expect(tracedColorForBlock("model")).not.toBe(tracedColorForBlock("input"));
    expect(tracedColorForBlock("block")).toBe(tracedColorForBlock(null));
    expect(tracedColorForBlock("unknown-kind")).toBe(tracedColorForBlock(null));
  });
});

describe("buildSegmentModel", () => {
  it("extrudes a unit-footprint solid on a y=0 base", () => {
    const model = buildSegmentModel(
      [
        [0.1, 0.2],
        [0.4, 0.2],
        [0.4, 0.6],
        [0.1, 0.6],
      ],
      "nmos",
    );
    expect(model).not.toBeNull();
    if (!model) return;
    const box = new THREE.Box3().setFromObject(model);
    const size = new THREE.Vector3();
    box.getSize(size);
    expect(Math.max(size.x, size.z)).toBeCloseTo(1, 1);
    expect(box.min.y).toBeCloseTo(0, 2);
    expect(size.y).toBeGreaterThan(0.3);
    expect(size.y).toBeLessThan(0.7);
    const mesh = model.children.find((child) => child instanceof THREE.Mesh);
    expect(mesh).toBeDefined();
    const material = (mesh as THREE.Mesh).material;
    expect(material instanceof THREE.MeshStandardMaterial).toBe(true);
    expect((material as THREE.MeshStandardMaterial).color.getHex()).toBe(
      tracedColorForBlock("nmos"),
    );
  });

  it("returns null for degenerate outlines", () => {
    expect(buildSegmentModel([])).toBeNull();
    expect(
      buildSegmentModel([
        [0.5, 0.5],
        [0.5, 0.5],
        [0.5, 0.5],
      ]),
    ).toBeNull();
    expect(
      buildSegmentModel([
        [0.1, 0.1],
        [0.9, 0.1],
      ]),
    ).toBeNull();
  });
});
