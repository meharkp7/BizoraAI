import { describe, expect, it } from "vitest";
import {
  dimsText,
  isWeightMatrix,
  nestedFootprintScales,
  nestedGrid,
  nestedLabel,
  nestedTagLift,
  unitlessArea,
} from "./nestedLayout.ts";

describe("unitlessArea", () => {
  it("reads unitless w*h and rejects everything else", () => {
    expect(unitlessArea({ w: 4096, h: 4096, unit: null })).toBe(4096 * 4096);
    expect(unitlessArea({ w: 1024, h: 4096 })).toBe(1024 * 4096);
    expect(unitlessArea(null)).toBeNull();
    expect(unitlessArea(undefined)).toBeNull();
    expect(unitlessArea({ w: 900, h: 600, unit: "um" })).toBeNull();
    expect(unitlessArea({ w: 4096, h: null, unit: null })).toBeNull();
    expect(unitlessArea({ w: -4, h: 3, unit: null })).toBeNull();
    expect(unitlessArea({ w: NaN, h: 3, unit: null })).toBeNull();
  });
});

describe("nestedFootprintScales", () => {
  it("stays uniform when no sibling states dims", () => {
    expect(nestedFootprintScales([null, undefined, { w: 4, h: 3, unit: "um" }])).toEqual([
      1, 1, 1,
    ]);
  });

  it("normalizes log-area across siblings within a readable band", () => {
    // Q 4096x4096, K 1024x4096, Up 14336x4096: Up largest, K
    // smallest, all inside [0.55, 1].
    const scales = nestedFootprintScales([
      { w: 4096, h: 4096, unit: null },
      { w: 1024, h: 4096, unit: null },
      { w: 14336, h: 4096, unit: null },
    ]);
    expect(scales[2]).toBeCloseTo(1);
    expect(scales[1]).toBeCloseTo(0.55);
    expect(scales[0]).toBeGreaterThan(scales[1]);
    expect(scales[0]).toBeLessThan(scales[2]);
  });

  it("gives unknown siblings the sibling mean", () => {
    const scales = nestedFootprintScales([
      { w: 1024, h: 1024, unit: null },
      null,
      { w: 16384, h: 16384, unit: null },
    ]);
    expect(scales[1]).toBeCloseTo((scales[0] + scales[2]) / 2);
  });

  it("treats identical areas as full size", () => {
    expect(
      nestedFootprintScales([
        { w: 4096, h: 4096, unit: null },
        { w: 4096, h: 4096, unit: null },
      ]),
    ).toEqual([1, 1]);
  });
});

describe("nestedGrid", () => {
  it("keeps the root grid on square parents", () => {
    expect(nestedGrid(7, 22, 22)).toEqual({ cols: 3, rows: 3 });
    expect(nestedGrid(4, 10, 10)).toEqual({ cols: 2, rows: 2 });
    expect(nestedGrid(2, 10, 10)).toEqual({ cols: 2, rows: 1 });
    expect(nestedGrid(1, 10, 10)).toEqual({ cols: 1, rows: 1 });
  });

  it("balances columns by aspect on strips", () => {
    // Seven matrices on a 22-wide, 33-deep strip: 2 columns of 4.
    expect(nestedGrid(7, 22, 33)).toEqual({ cols: 2, rows: 4 });
    // Same seven on a wide shallow strip: 5 columns of 2.
    expect(nestedGrid(7, 44, 11)).toEqual({ cols: 5, rows: 2 });
  });

  it("never proposes empty or over-wide grids", () => {
    expect(nestedGrid(0, 10, 10)).toEqual({ cols: 1, rows: 1 });
    expect(nestedGrid(3, 10, 0)).toEqual({ cols: 3, rows: 1 });
  });
});

describe("nestedTagLift", () => {
  it("staggers sibling tags across three heights", () => {
    expect([0, 1, 2, 3, 4].map(nestedTagLift)).toEqual([1.5, 4.5, 7.5, 1.5, 4.5]);
  });
});

describe("nestedLabel", () => {
  it("suffixes stated dims and leaves the rest alone", () => {
    expect(nestedLabel("Up", { w: 14336, h: 4096, unit: null })).toBe("Up · 14336×4096");
    expect(nestedLabel("Q", { w: 4096, h: 4096, unit: null })).toBe("Q · 4096×4096");
    expect(nestedLabel("weight block", { w: 4, h: 3, unit: "um" })).toBe(
      "weight block · 4×3 um",
    );
    expect(nestedLabel("Q", null)).toBe("Q");
    expect(nestedLabel("Q", { w: 4096, h: null, unit: null })).toBe("Q");
  });

  it("formats fractional extents compactly", () => {
    expect(dimsText({ w: 2.5, h: 10, unit: null })).toBe("2.5×10");
  });
});

describe("isWeightMatrix", () => {
  it("recognizes childless modules with matrix-sized unitless dims", () => {
    expect(isWeightMatrix("module", { w: 4096, h: 4096, unit: null }, 0)).toBe(true);
    expect(isWeightMatrix("module", { w: 1024, h: 4096 }, 0)).toBe(true);
    expect(isWeightMatrix("module", { w: 14336, h: 4096, unit: null }, 0)).toBe(true);
  });

  it("rejects containers, physical dims, and small shapes", () => {
    expect(isWeightMatrix("module", { w: 4096, h: 4096, unit: null }, 2)).toBe(false);
    expect(isWeightMatrix("module", { w: 900, h: 600, unit: "um" }, 0)).toBe(false);
    expect(isWeightMatrix("module", { w: 4, h: 3, unit: null }, 0)).toBe(false);
    expect(isWeightMatrix("module", null, 0)).toBe(false);
    expect(isWeightMatrix("part", { w: 4096, h: 4096, unit: null }, 0)).toBe(false);
    expect(isWeightMatrix("cell", { w: 4096, h: 4096, unit: null }, 0)).toBe(false);
  });
});
