import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { HomePage } from "./HomePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

async function attachPaper() {
  const file = new File(["%PDF-1.4 fake"], "paper.pdf", { type: "application/pdf" });
  const user = userEvent.setup();
  const form = screen.getByRole("form", { name: "Upload a paper" });
  const upload = within(form).getByLabelText("Paper (PDF)");
  await user.upload(upload, file);
  // Parsing prefills the title and suggested identifiers.
  await within(form).findByDisplayValue("Vision transformer");
  return user;
}

describe("HomePage upload", () => {
  it("parses a paper then uploads with prefilled identifiers", async () => {
    render(<HomePage />, { wrapper });
    const user = await attachPaper();
    const form = screen.getByRole("form", { name: "Upload a paper" });

    expect(within(form).getByLabelText("Project ID (optional)")).toHaveValue(
      "vision-transformer-00000000",
    );

    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    const summary = await screen.findByText("Vision transformer");
    const status = summary.closest("[role='status']") as HTMLElement;
    expect(status).toHaveTextContent("1 table(s)");
    expect(
      within(status).getByRole("button", { name: "Open workspace" }),
    ).toBeInTheDocument();
  });

  it("uploads with just the file when fields stay blank", async () => {
    render(<HomePage />, { wrapper });
    const file = new File(["%PDF-1.4 fake"], "paper.pdf", { type: "application/pdf" });
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Upload a paper" });
    await user.upload(within(form).getByLabelText("Paper (PDF)"), file);

    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    expect(await screen.findByText(/Extracted /)).toBeInTheDocument();
  });

  it("shows the rejection when extraction fails", async () => {
    server.use(
      http.post("/api/v1/papers/extract", () =>
        HttpResponse.json(
          { error: { code: "INVALID_REQUEST", message: "Not a PDF.", details: {} } },
          { status: 422 },
        ),
      ),
    );
    render(<HomePage />, { wrapper });
    const user = await attachPaper();

    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_REQUEST");
  });
});
