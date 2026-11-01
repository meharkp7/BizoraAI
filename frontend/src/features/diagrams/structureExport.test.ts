import { describe, expect, it } from "vitest";
import type { Point3, Projected, SvgPart, SvgWire } from "./structureExport.ts";
import { buildStructureSvg, structureFilename } from "./structureExport.ts";

/** Fake orthographic projection: x -> x, y -> -y, depth = z. */
function ortho(point: Point3): Projected | null {
  return { x: point[0], y: -point[1], z: point[2] };
}

function part(label: string, z: number, color = "#b87333"): SvgPart {
  return {
    label,
    color,
    corners: [
      [10, 10, z],
      [30, 10, z],
      [10, 30, z],
      [30, 30, z],
    ],
  };
}

function wire(net: string): SvgWire {
  return {
    net,
    color: "#b03a2e",
    legs: [{ hub: [0, 0, 5], mid: [15, -20, 5], spoke: [30, 0, 5] }],
  };
}

describe("buildStructureSvg", () => {
  it("draws part bounds with labels and net arcs with net names", () => {
    const svg = buildStructureSvg({
      title: "Circuit 3D",
      caption: "Projected vector snapshot",
      width: 800,
      height: 600,
      background: "#faf7ec",
      parts: [part("K1 (pmos)", 5)],
      wires: [wire("En")],
      project: ortho,
    });
    expect(svg).toContain("<svg");
    expect(svg).toContain("K1 (pmos)");
    expect(svg).toContain("<rect");
    expect(svg).toContain("<polyline");
    expect(svg).toContain("Net En");
    expect(svg).toContain("#b03a2e");
  });

  it("paints far parts before near ones", () => {
    const svg = buildStructureSvg({
      title: "t",
      caption: "",
      width: 800,
      height: 600,
      background: "#fff",
      parts: [part("near", 1), part("far", 9)],
      wires: [],
      project: ortho,
    });
    expect(svg.indexOf("far")).toBeLessThan(svg.indexOf("near"));
  });

  it("drops legs with an endpoint behind the camera and escapes labels", () => {
    const svg = buildStructureSvg({
      title: "A&B <test>",
      caption: "",
      width: 800,
      height: 600,
      background: "#fff",
      parts: [],
      wires: [wire("En")],
      project: (point) => (point[0] === 15 ? null : ortho(point)),
    });
    expect(svg).not.toContain("<polyline");
    expect(svg).toContain("A&amp;B &lt;test&gt;");
  });
});

describe("structureFilename", () => {
  it("slugs the scene title", () => {
    expect(structureFilename("Typical metastability SRAM-based PUF cell.", "png")).toBe(
      "bizora-3d-typical-metastability-sram-based-puf-cell.png",
    );
    expect(structureFilename("Cell interior", "svg")).toBe("bizora-3d-cell-interior.svg");
  });
});
