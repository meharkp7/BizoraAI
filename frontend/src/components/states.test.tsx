import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "./states.tsx";

describe("state components", () => {
  it("announces loading politely", () => {
    render(<LoadingState label="Loading revision…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading revision…");
  });

  it("alerts errors with an optional retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Boom." detail="Gone wrong." onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Boom.");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders empty states without actions", () => {
    render(<EmptyState title="Nothing here." detail="Come back later." />);
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
