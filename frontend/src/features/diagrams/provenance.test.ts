import { describe, expect, it } from "vitest";
import {
  countProvenance,
  elementProvenance,
  figureIdFromSource,
  hasEvidence,
} from "./provenance.ts";

describe("diagram provenance", () => {
  it("marks evidenced, confident elements as from paper", () => {
    expect(elementProvenance({ page: 2 }, 0.9)).toBe("from-paper");
    expect(elementProvenance({ figure_id: "f1" }, 0.6)).toBe("from-paper");
    expect(elementProvenance({ quote: "cells" }, 1)).toBe("from-paper");
  });

  it("marks missing evidence or low confidence as assumed", () => {
    expect(elementProvenance(null, 0.99)).toBe("assumed");
    expect(elementProvenance({ page: null, figure_id: null, quote: null }, 0.99)).toBe(
      "assumed",
    );
    expect(elementProvenance({ page: 2 }, 0.59)).toBe("assumed");
    expect(elementProvenance({ page: 2 }, null)).toBe("from-paper");
  });

  it("counts a view's labels", () => {
    expect(
      countProvenance([
        { evidence: { page: 1 }, confidence: 0.9 },
        { evidence: null, confidence: 0.9 },
        { evidence: { page: 1 }, confidence: 0.2 },
      ]),
    ).toEqual({ fromPaper: 1, assumed: 2 });
  });

  it("detects evidence presence", () => {
    expect(hasEvidence(null)).toBe(false);
    expect(hasEvidence(undefined)).toBe(false);
    expect(hasEvidence({})).toBe(false);
    expect(hasEvidence({ page: 3 })).toBe(true);
  });

  it("parses figure sources", () => {
    expect(figureIdFromSource("figure:fig-1")).toBe("fig-1");
    expect(figureIdFromSource("text")).toBeNull();
    expect(figureIdFromSource(undefined)).toBeNull();
    expect(figureIdFromSource("figure:")).toBeNull();
  });
});
