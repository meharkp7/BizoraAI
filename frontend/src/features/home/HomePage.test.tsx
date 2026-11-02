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

describe("HomePage upload queue", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("extracts several papers in turn with per-file progress", async () => {
    let extracts = 0;
    server.use(
      http.post("/api/v1/papers/extract", async () => {
        extracts += 1;
        return HttpResponse.json(
          {
            graph: {
              project_id: `p-${extracts}`,
              graph_id: `g-${extracts}`,
              version: 1,
              title: `Queued paper ${extracts}`,
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
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Upload a paper" });
    const first = new File(["%PDF-1.4 one"], "one.pdf", { type: "application/pdf" });
    const second = new File(["%PDF-1.4 two"], "two.pdf", { type: "application/pdf" });
    await user.upload(within(form).getByLabelText("Paper (PDF)"), [first, second]);

    expect(await within(form).findByText("0 of 2 extracted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upload and extract" }));

    expect(await within(form).findByText("2 of 2 extracted")).toBeInTheDocument();
    expect(extracts).toBe(2);
    expect(await within(form).findByText("Queued paper 1")).toBeInTheDocument();
    expect(await within(form).findByText("Queued paper 2")).toBeInTheDocument();
  });

  it("warns when a file was already extracted", async () => {
    server.use(
      http.post("/api/v1/papers/parse", () =>
        HttpResponse.json({
          filename: "paper.pdf",
          title: "Vision transformer",
          authors: [],
          page_count: 12,
          chars: 42000,
          sha256: "0".repeat(64),
          truncated: false,
          suggested: {
            project_id: "vision-transformer-00000000",
            graph_id: "vision-transformer-graph-00000000",
            source_id: "paper-00000000",
          },
          duplicate_of: {
            project_id: "project-1",
            graph_id: "graph-1",
            source_id: "paper-1",
            title: "Earlier upload",
            workspace_path: "/g/project-1/graph-1",
          },
        }),
      ),
    );
    render(<HomePage />, { wrapper });
    const file = new File(["%PDF-1.4 fake"], "paper.pdf", { type: "application/pdf" });
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Upload a paper" });
    await user.upload(within(form).getByLabelText("Paper (PDF)"), file);

    expect(await within(form).findByText(/Already extracted as/)).toBeInTheDocument();
    expect(
      within(form).getByRole("link", { name: "Open existing workspace" }),
    ).toHaveAttribute("href", "/g/project-1/graph-1");
  });
});

describe("HomePage import", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("imports a paper from an arXiv ID", async () => {
    render(<HomePage />, { wrapper });
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Import a paper from a link" });
    await user.type(
      within(form).getByLabelText("ArXiv ID, DOI, or URL"),
      "1706.03762v7",
    );
    await user.click(screen.getByRole("button", { name: "Import and extract" }));

    const summary = await screen.findByText(/Imported from /);
    const status = summary.closest("[role='status']") as HTMLElement;
    expect(status).toHaveTextContent("https://arxiv.org/pdf/1706.03762v7");
    expect(status).toHaveTextContent("Vision transformer");
    expect(
      within(status).getByRole("button", { name: "Open workspace" }),
    ).toBeInTheDocument();
  });

  it("shows the rejection when import fails", async () => {
    server.use(
      http.post("/api/v1/papers/import", () =>
        HttpResponse.json(
          { error: { code: "INVALID_REQUEST", message: "Bad source.", details: {} } },
          { status: 422 },
        ),
      ),
    );
    render(<HomePage />, { wrapper });
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Import a paper from a link" });
    await user.type(within(form).getByLabelText("ArXiv ID, DOI, or URL"), "nope");
    await user.click(screen.getByRole("button", { name: "Import and extract" }));

    const section = screen.getByRole("region", { name: "Import a paper" });
    expect(await within(section).findByRole("alert")).toHaveTextContent("INVALID_REQUEST");
  });
});

describe("HomePage sample paper", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("links to the seeded sample workspace", async () => {
    server.use(
      http.get("/api/v1/papers/sample", () =>
        HttpResponse.json({
          project_id: "project-1",
          graph_id: "graph-1",
          source_id: "paper-1",
          title: "SRAM PUF",
          workspace_path: "/g/project-1/graph-1",
          available: true,
        }),
      ),
    );
    render(<HomePage />, { wrapper });

    const section = screen.getByRole("region", { name: "Sample paper" });
    expect(await within(section).findByRole("link", { name: /SRAM PUF/ })).toHaveAttribute(
      "href",
      "/g/project-1/graph-1",
    );
  });

  it("explains how to seed the sample workspace", async () => {
    server.use(
      http.get("/api/v1/papers/sample", () =>
        HttpResponse.json({
          project_id: "project-1",
          graph_id: "graph-1",
          source_id: "paper-1",
          title: "SRAM PUF",
          workspace_path: "/g/project-1/graph-1",
          available: false,
        }),
      ),
    );
    render(<HomePage />, { wrapper });

    const section = screen.getByRole("region", { name: "Sample paper" });
    expect(await within(section).findByText(/not seeded yet/)).toBeInTheDocument();
    expect(within(section).getByText("scripts/seed_sample_paper.py")).toBeInTheDocument();
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
