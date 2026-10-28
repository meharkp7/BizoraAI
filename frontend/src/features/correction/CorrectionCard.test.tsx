import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GraphNode } from "../../lib/types.ts";
import { CorrectionCard } from "./CorrectionCard.tsx";

/** Clearly-marked fake: an assumed component with one evidence quote. */
function fakeAssumedNode(): GraphNode {
  return {
    id: "fake-node",
    kind: "component",
    label: "Fake widget",
    description: "A fake extracted widget.",
    config: { assumed: true, assumption_reason: "Fake reason.", setting: "kept" },
    input_shape: null,
    output_shape: null,
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
    provenance: "inferred",
    confidence: 0.4,
  };
}

function noop() {}

describe("CorrectionCard", () => {
  it("shows the assumed badge, reason, and evidence quote", () => {
    render(
      <CorrectionCard
        node={fakeAssumedNode()}
        decision={null}
        disabled={false}
        onAccept={noop}
        onReject={noop}
        onEdit={noop}
        onClear={noop}
      />,
    );

    expect(screen.getByText("Assumed")).toBeInTheDocument();
    expect(screen.getByText("Fake reason.")).toBeInTheDocument();
    expect(
      screen.getByText("The fake widget processes the input."),
    ).toBeInTheDocument();
    expect(screen.getByText("p. 2")).toBeInTheDocument();
  });

  it("marks ungrounded components without evidence", () => {
    render(
      <CorrectionCard
        node={{ ...fakeAssumedNode(), config: {}, evidence: [] }}
        decision={null}
        disabled={false}
        onAccept={noop}
        onReject={noop}
        onEdit={noop}
        onClear={noop}
      />,
    );

    expect(screen.getByText("No evidence")).toBeInTheDocument();
    expect(screen.getByText(/Treat its details as/)).toBeInTheDocument();
  });

  it("emits accept and reject decisions", () => {
    const onAccept = vi.fn();
    const onReject = vi.fn();
    render(
      <CorrectionCard
        node={fakeAssumedNode()}
        decision={null}
        disabled={false}
        onAccept={onAccept}
        onReject={onReject}
        onEdit={noop}
        onClear={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(onAccept).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onReject).toHaveBeenCalledOnce();
  });

  it("submits an edit with parsed configuration", () => {
    const onEdit = vi.fn();
    render(
      <CorrectionCard
        node={fakeAssumedNode()}
        decision={null}
        disabled={false}
        onAccept={noop}
        onReject={noop}
        onEdit={onEdit}
        onClear={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "Fake corrected widget" },
    });
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: { value: JSON.stringify({ setting: "changed" }) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    expect(onEdit).toHaveBeenCalledOnce();
    expect(onEdit).toHaveBeenCalledWith({
      label: "Fake corrected widget",
      description: "A fake extracted widget.",
      config: { setting: "changed" },
    });
  });

  it("rejects invalid configuration JSON and blank labels", () => {
    const onEdit = vi.fn();
    render(
      <CorrectionCard
        node={fakeAssumedNode()}
        decision={null}
        disabled={false}
        onAccept={noop}
        onReject={noop}
        onEdit={onEdit}
        onClear={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: { value: "{not json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("valid JSON");

    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: { value: "{}" },
    });
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("label is required");
  });

  it("shows the recorded decision with a clear action", () => {
    const onClear = vi.fn();
    render(
      <CorrectionCard
        node={fakeAssumedNode()}
        decision="accept"
        disabled={false}
        onAccept={noop}
        onReject={noop}
        onEdit={noop}
        onClear={onClear}
      />,
    );

    expect(screen.getByText("Decision: Accepted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear decision" }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});
