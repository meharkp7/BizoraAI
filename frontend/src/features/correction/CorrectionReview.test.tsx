import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GraphNode, MethodologyGraph } from "../../lib/types.ts";
import { CorrectionReview } from "./CorrectionReview.tsx";

/** Clearly-marked fake: one component under review. */
function fakeNode(id: string, overrides?: Partial<GraphNode>): GraphNode {
  return {
    id,
    kind: "component",
    label: `Fake ${id}`,
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

/** Clearly-marked fake: a revision mixing assumed, bare, and grounded claims. */
function fakeGraph(): MethodologyGraph {
  return {
    schema_version: "1.0",
    project_id: "fake-project",
    graph_id: "fake-graph",
    version: 1,
    title: "Fake methodology",
    source_ids: ["fake-paper"],
    nodes: [
      fakeNode("fake-alpha", {
        config: { assumed: true, assumption_reason: "Fake reason." },
        provenance: "inferred",
      }),
      fakeNode("fake-beta"),
      fakeNode("fake-gamma", {
        evidence: [
          {
            source_id: "fake-paper",
            page: 2,
            quote: "The fake gamma widget is described here.",
            figure_label: null,
            bbox: null,
            locator: null,
            status: "supported",
          },
        ],
        provenance: "extracted",
      }),
    ],
    edges: [],
    created_by: "fake-user",
    parent_version: null,
  };
}

function card(label: string) {
  return screen.getByRole("article", { name: label });
}

describe("CorrectionReview", () => {
  it("tracks decisions per component and submits one batch", () => {
    const onSubmit = vi.fn();
    render(
      <CorrectionReview
        graph={fakeGraph()}
        pending={false}
        error={null}
        savedVersion={null}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText(/0 of 3 components decided/)).toBeInTheDocument();
    expect(screen.getByText(/2 need review/)).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: "Submit corrections" });
    expect(submit).toBeDisabled();

    fireEvent.click(within(card("Fake fake-alpha")).getByRole("button", { name: "Accept" }));
    fireEvent.click(within(card("Fake fake-beta")).getByRole("button", { name: "Reject" }));
    expect(screen.getByText(/2 of 3 components decided/)).toBeInTheDocument();

    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledOnce();
    const patches = onSubmit.mock.calls[0][0];
    expect(patches).toHaveLength(2);
    for (const patch of patches) {
      expect(patch.base_version).toBe(1);
      expect(patch.requested_by).toBe("correction-ui");
    }
    expect(patches.map((patch: { operation: string }) => patch.operation).sort()).toEqual([
      "remove_node",
      "replace_node",
    ]);
  });

  it("clears a decision and disables submit when none remain", () => {
    const onSubmit = vi.fn();
    render(
      <CorrectionReview
        graph={fakeGraph()}
        pending={false}
        error={null}
        savedVersion={null}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(within(card("Fake fake-alpha")).getByRole("button", { name: "Accept" }));
    expect(screen.getByText(/1 of 3 components decided/)).toBeInTheDocument();
    fireEvent.click(
      within(card("Fake fake-alpha")).getByRole("button", { name: "Clear decision" }),
    );
    expect(screen.getByText(/0 of 3 components decided/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit corrections" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("reports the saved revision and submit errors", () => {
    const { rerender } = render(
      <CorrectionReview
        graph={fakeGraph()}
        pending={false}
        error={null}
        savedVersion={2}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText("Corrections saved as revision 2.")).toBeInTheDocument();

    rerender(
      <CorrectionReview
        graph={fakeGraph()}
        pending={false}
        error="Fake submit failure."
        savedVersion={null}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Fake submit failure.");
  });

  it("shows an empty state for revisions without components", () => {
    render(
      <CorrectionReview
        graph={{ ...fakeGraph(), nodes: [] }}
        pending={false}
        error={null}
        savedVersion={null}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText("No components in this revision.")).toBeInTheDocument();
  });
});
