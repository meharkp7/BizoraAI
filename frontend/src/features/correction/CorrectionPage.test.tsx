import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { CorrectionPage } from "./CorrectionPage.tsx";

/* The shared MSW server mocks the revision and patch-batch endpoints,
   so this page test uses fixtures only and makes zero live calls. */

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CorrectionPage", () => {
  it("reviews extracted components and saves corrections as a new revision", async () => {
    render(<CorrectionPage projectId="project-1" graphId="graph-1" version={2} />, {
      wrapper,
    });

    expect(await screen.findByRole("heading", { name: "Review extraction" })).toBeInTheDocument();
    expect(screen.getByText(/revision 2/)).toBeInTheDocument();

    const inputCard = await screen.findByRole("article", { name: "Image" });
    expect(within(inputCard).getByText("No evidence")).toBeInTheDocument();
    const encoderCard = screen.getByRole("article", { name: "Transformer encoder" });
    expect(
      within(encoderCard).getByText("The encoder stacks twelve blocks."),
    ).toBeInTheDocument();

    fireEvent.click(within(inputCard).getByRole("button", { name: "Accept" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit corrections" }));

    expect(await screen.findByText("Corrections saved as revision 3.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to workspace" })).toHaveAttribute(
      "href",
      "/g/project-1/graph-1?v=3",
    );
  });

  it("reports a missing revision with recovery", async () => {
    render(<CorrectionPage projectId="project-1" graphId="graph-1" version={9} />, {
      wrapper,
    });

    expect(await screen.findByText("Revision 9 does not exist.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
