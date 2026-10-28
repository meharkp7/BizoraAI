import { describe, expect, it } from "vitest";
import type { GraphNode } from "../../lib/types.ts";
import {
  assumptionReason,
  hasEvidence,
  isAssumed,
  needsReview,
} from "./assumptions.ts";

/** Clearly-marked fake: one extracted component for assumption tests. */
function fakeNode(overrides?: Partial<GraphNode>): GraphNode {
  return {
    id: "fake-node",
    kind: "component",
    label: "Fake widget",
    description: null,
    config: {},
    input_shape: null,
    output_shape: null,
    evidence: [],
    provenance: "unresolved",
    confidence: null,
    ...overrides,
  };
}

describe("correction assumptions", () => {
  it("reads an explicit assumed flag and reason", () => {
    const node = fakeNode({
      config: { assumed: true, assumption_reason: "Fake reason." },
    });
    expect(isAssumed(node)).toBe(true);
    expect(assumptionReason(node)).toBe("Fake reason.");
    expect(needsReview(node)).toBe(true);
  });

  it("treats missing or non-true flags as not assumed", () => {
    expect(isAssumed(fakeNode())).toBe(false);
    expect(isAssumed(fakeNode({ config: { assumed: false } }))).toBe(false);
    expect(isAssumed(fakeNode({ config: { assumed: 1 } }))).toBe(false);
    expect(assumptionReason(fakeNode())).toBeNull();
    expect(assumptionReason(fakeNode({ config: { assumption_reason: "  " } }))).toBeNull();
  });

  it("flags ungrounded nodes for review even without a flag", () => {
    expect(hasEvidence(fakeNode())).toBe(false);
    expect(needsReview(fakeNode())).toBe(true);
  });

  it("passes evidence-backed, unflagged nodes as reviewed", () => {
    const node = fakeNode({
      evidence: [
        {
          source_id: "fake-paper",
          page: 2,
          quote: "The fake widget processes the input.",
          figure_label: null,
          bbox: null,
          locator: null,
          status: "supported",
        },
      ],
      provenance: "extracted",
    });
    expect(hasEvidence(node)).toBe(true);
    expect(needsReview(node)).toBe(false);
  });

  it("still flags evidence-backed nodes the extractor marked assumed", () => {
    const node = fakeNode({
      config: { assumed: true, assumption_reason: "Fake uncertain reason." },
      evidence: [
        {
          source_id: "fake-paper",
          page: 2,
          quote: "A partial fake mention.",
          figure_label: null,
          bbox: null,
          locator: null,
          status: "partial",
        },
      ],
    });
    expect(needsReview(node)).toBe(true);
  });
});
