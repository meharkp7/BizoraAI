import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken, setAuthToken } from "../../lib/authToken.ts";
import { useSession } from "../../lib/store.ts";
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
  // Parsing prefills the title; identifiers stay internal.
  await within(form).findByDisplayValue("Vision transformer");
  return user;
}

describe("HomePage upload", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("parses a paper then uploads with a prefilled title", async () => {
    render(<HomePage />, { wrapper });
    const user = await attachPaper();
    const form = screen.getByRole("form", { name: "Upload a paper" });

    expect(within(form).getByLabelText("Title")).toHaveValue("Vision transformer");
    expect(within(form).queryByLabelText(/Project ID/)).toBeNull();

    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    const summary = await screen.findByText("Vision transformer");
    const status = summary.closest("[role='status']") as HTMLElement;
    expect(status).toHaveTextContent("1 table(s)");
    expect(
      within(status).getByRole("button", { name: "Open workspace" }),
    ).toBeInTheDocument();
  });

  it("sends no identifiers: they stay internal", async () => {
    const seen: Record<string, string>[] = [];
    server.use(
      http.post("/api/v1/papers/extract", async ({ request }) => {
        const form = await request.formData();
        seen.push(Object.fromEntries(form.entries()) as Record<string, string>);
        return HttpResponse.json(
          {
            graph: {
              project_id: "p",
              graph_id: "g",
              version: 1,
              title: "Vision transformer",
              nodes: [],
            },
            tables: [],
            warnings: [],
            page_count: 1,
            truncated: false,
          },
          { status: 201 },
        );
      }),
    );
    render(<HomePage />, { wrapper });
    const user = await attachPaper();

    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    expect(await screen.findByText(/Extracted /)).toBeInTheDocument();
    expect(seen).toHaveLength(1);
    expect(seen[0]).not.toHaveProperty("project_id");
    expect(seen[0]).not.toHaveProperty("graph_id");
    expect(seen[0]).not.toHaveProperty("source_id");
    expect(seen[0]).not.toHaveProperty("created_by");
    expect(seen[0]["title"]).toBe("Vision transformer");
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

describe("HomePage library", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("nudges logged-out visitors to log in", () => {
    render(<HomePage />, { wrapper });
    const section = screen.getByRole("region", { name: "My papers" });
    expect(within(section).getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("lists the caller's papers when logged in", async () => {
    setAuthToken("test-token");
    useSession.setState({ token: "test-token" });
    render(<HomePage />, { wrapper });

    const section = screen.getByRole("region", { name: "My papers" });
    expect(
      await within(section).findByRole("link", { name: "AlphaFold paper" }),
    ).toHaveAttribute("href", "/g/project-papers/graph-papers");
  });
});
