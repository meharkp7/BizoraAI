import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SymbolGlyph } from "./CategoryGlyph.tsx";

describe("SymbolGlyph", () => {
  it("draws distinct art per schematic and process symbol", () => {
    const arts = new Set(
      [
        "transistor",
        "bitcell",
        "gate",
        "senseamp",
        "meter",
        "passive",
        "diode",
        "chip",
        "adc",
        "source",
        "bias",
        "dataset",
        "preprocessing",
        "operation",
        "loss",
        "optimizer",
        "evaluation",
        "tensor",
        "format",
        "engine",
        "channel",
        "cloud",
      ].map((symbol) => render(<SymbolGlyph symbol={symbol} />).container.innerHTML),
    );
    expect(arts.size).toBe(22);
  });

  it("shares one gauge for both evaluator spellings", () => {
    expect(render(<SymbolGlyph symbol="evaluator" />).container.innerHTML).toBe(
      render(<SymbolGlyph symbol="evaluation" />).container.innerHTML,
    );
  });

  it("falls back to the generic ring for 3D-only and unknown symbols", () => {
    const generic = render(<SymbolGlyph symbol="generic" />).container.innerHTML;
    expect(render(<SymbolGlyph symbol="attention" />).container.innerHTML).toBe(generic);
    expect(render(<SymbolGlyph symbol="quantum-foam" />).container.innerHTML).toBe(generic);
  });
});
