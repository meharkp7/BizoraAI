import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceBadge } from "./ProvenanceBadge.tsx";

describe("ProvenanceBadge", () => {
  it("renders each honesty label", () => {
    const { rerender } = render(<ProvenanceBadge provenance="measured" />);
    expect(screen.getByText("Measured")).toBeInTheDocument();
    rerender(<ProvenanceBadge provenance="assumed" />);
    expect(screen.getByText("Assumed")).toBeInTheDocument();
    rerender(<ProvenanceBadge provenance="illustrative" />);
    expect(screen.getByText("Illustrative")).toBeInTheDocument();
  });

  it("prefers an explicit reason for the tooltip", () => {
    render(<ProvenanceBadge provenance="assumed" reason="Assumed comparable." />);
    expect(screen.getByText("Assumed")).toHaveAttribute("title", "Assumed comparable.");
  });
});
