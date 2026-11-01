import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceLegend, ProvenanceTag } from "./ProvenanceTag.tsx";

describe("ProvenanceTag", () => {
  it("labels each value plainly", () => {
    const { rerender } = render(<ProvenanceTag value="from-paper" />);
    expect(screen.getByText("from paper")).toHaveAttribute(
      "title",
      "Traced to a paper figure, page, or quote.",
    );
    rerender(<ProvenanceTag value="assumed" />);
    expect(screen.getByText("assumed")).toBeInTheDocument();
    rerender(<ProvenanceTag value="illustrative" />);
    expect(screen.getByText("illustrative")).toBeInTheDocument();
  });

  it("defines all three labels in the legend", () => {
    render(<ProvenanceLegend />);
    expect(screen.getByText("from paper")).toBeInTheDocument();
    expect(screen.getByText("traced to a figure, page, or quote")).toBeInTheDocument();
    expect(screen.getByText("low confidence or no evidence")).toBeInTheDocument();
    expect(screen.getByText("computed layout, not in the paper")).toBeInTheDocument();
  });
});
