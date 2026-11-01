import { describe, expect, it } from "vitest";
import { pickSvgId } from "./svgPick.ts";

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) };
}

describe("pickSvgId", () => {
  it("resolves direct hits through the engine groups", () => {
    const container = document.createElement("div");
    container.innerHTML = `<svg><g data-id="m1"><path d="M0 0h1"/></g></svg>`;
    const path = container.querySelector("path");
    expect(pickSvgId(container, path, { x: 5, y: 5 }, "data-id")).toBe("m1");
  });

  it("accepts near misses such as sibling labels", () => {
    const container = document.createElement("div");
    container.innerHTML = `<svg><g data-id="m1"></g><text>M1</text></svg>`;
    const group = container.querySelector("g") as SVGGElement;
    group.getBoundingClientRect = () => rect(100, 100, 40, 40);
    const label = container.querySelector("text");
    // 10px right of the symbol box: the label seat.
    expect(pickSvgId(container, label, { x: 150, y: 120 }, "data-id")).toBe("m1");
  });

  it("ignores clicks far from every group", () => {
    const container = document.createElement("div");
    container.innerHTML = `<svg><g data-id="m1"></g></svg>`;
    const group = container.querySelector("g") as SVGGElement;
    group.getBoundingClientRect = () => rect(100, 100, 40, 40);
    expect(pickSvgId(container, container, { x: 500, y: 500 }, "data-id")).toBeNull();
  });

  it("skips unmeasurable groups", () => {
    const container = document.createElement("div");
    container.innerHTML = `<svg><g data-id="m1"></g></svg>`;
    const group = container.querySelector("g") as SVGGElement;
    group.getBoundingClientRect = () => rect(0, 0, 0, 0);
    expect(pickSvgId(container, container, { x: 0, y: 0 }, "data-id")).toBeNull();
  });
});
