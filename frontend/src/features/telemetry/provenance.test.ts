import { describe, expect, it } from "vitest";
import {
  provenanceDescription,
  provenanceLabel,
  resolveVisualProvenance,
} from "./provenance.ts";

describe("resolveVisualProvenance", () => {
  it("labels plain run observations measured", () => {
    expect(resolveVisualProvenance({})).toBe("measured");
    expect(resolveVisualProvenance({ resultKind: "measured" })).toBe("measured");
  });

  it("keeps stand-ins illustrative above all else", () => {
    expect(resolveVisualProvenance({ illustrative: true, assumed: true })).toBe(
      "illustrative",
    );
    expect(
      resolveVisualProvenance({ illustrative: true, resultKind: "measured" }),
    ).toBe("illustrative");
  });

  it("maps assumed flags and estimates to assumed", () => {
    expect(resolveVisualProvenance({ assumed: true })).toBe("assumed");
    expect(resolveVisualProvenance({ resultKind: "estimated" })).toBe("assumed");
    expect(resolveVisualProvenance({ resultKind: "hypothesis" })).toBe("assumed");
  });
});

describe("provenance wording", () => {
  it("covers every label with badge text and tooltip", () => {
    expect(provenanceLabel("measured")).toBe("Measured");
    expect(provenanceLabel("assumed")).toBe("Assumed");
    expect(provenanceLabel("illustrative")).toBe("Illustrative");
    for (const provenance of ["measured", "assumed", "illustrative"] as const) {
      expect(provenanceDescription(provenance).length).toBeGreaterThan(0);
    }
  });
});
