import { describe, expect, it } from "vitest";
import { isValidNodeId, suggestEdgeId, suggestNodeId } from "./ids.ts";

describe("canvas id helpers", () => {
  it("validates node ids like the backend contract", () => {
    expect(isValidNodeId("node-1")).toBe(true);
    expect(isValidNodeId("a".repeat(128))).toBe(true);
    expect(isValidNodeId("")).toBe(false);
    expect(isValidNodeId("-lead")).toBe(false);
    expect(isValidNodeId("has space")).toBe(false);
    expect(isValidNodeId("a".repeat(129))).toBe(false);
  });

  it("suggests the smallest free node id", () => {
    expect(suggestNodeId(new Set())).toBe("node-1");
    expect(suggestNodeId(new Set(["node-1", "node-2"]))).toBe("node-3");
    expect(suggestNodeId(new Set(["node-2"]))).toBe("node-1");
  });

  it("derives edge ids from endpoints with suffix fallback", () => {
    expect(suggestEdgeId("a", "b", new Set())).toBe("e-a-b");
    expect(suggestEdgeId("a", "b", new Set(["e-a-b"]))).toBe("e-a-b-2");
    const long = suggestEdgeId("x".repeat(200), "y", new Set());
    expect(long.length).toBeLessThanOrEqual(128);
    expect(isValidNodeId(long)).toBe(true);
  });
});
