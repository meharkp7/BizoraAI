import { expect, test } from "@playwright/test";

const parsePayload = {
  filename: "paper.pdf",
  title: "Stubbed paper",
  authors: [],
  page_count: 3,
  chars: 1200,
  sha256: "0".repeat(64),
  truncated: false,
  suggested: {
    project_id: "stubbed-paper-00000000",
    graph_id: "stubbed-paper-graph-00000000",
    source_id: "paper-00000000",
  },
  duplicate_of: null,
};

function extractionPayload(title: string, suffix: string) {
  return {
    graph: {
      project_id: `project-${suffix}`,
      graph_id: `graph-${suffix}`,
      version: 1,
      title,
      source_ids: [`paper-${suffix}`],
      nodes: [],
      edges: [],
      created_by: "paper-upload",
      parent_version: null,
    },
    tables: [],
    warnings: [],
    page_count: 3,
    truncated: false,
  };
}

test("multi-file upload extracts each paper with progress", async ({ page }) => {
  let extracts = 0;
  await page.route("**/api/v1/papers/parse", async (route) => {
    await route.fulfill({ json: parsePayload });
  });
  await page.route("**/api/v1/papers/extract", async (route) => {
    extracts += 1;
    await route.fulfill({
      status: 201,
      json: extractionPayload(`Queued paper ${extracts}`, `q${extracts}`),
    });
  });
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Sample",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });

  await page.goto("/papers");
  await page
    .getByLabel("Paper (PDF)")
    .setInputFiles([
      { name: "one.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 one") },
      { name: "two.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 two") },
    ]);

  const form = page.getByRole("form", { name: "Upload a paper" });
  await expect(form.getByText("0 of 2 extracted")).toBeVisible();
  await page.getByRole("button", { name: "Upload and extract" }).click();

  await expect(form.getByText("2 of 2 extracted")).toBeVisible();
  await expect(form.getByText("Queued paper 1")).toBeVisible();
  await expect(form.getByText("Queued paper 2")).toBeVisible();
  expect(extracts).toBe(2);
});

test("upload warns on an already-extracted duplicate", async ({ page }) => {
  await page.route("**/api/v1/papers/parse", async (route) => {
    await route.fulfill({
      json: {
        ...parsePayload,
        duplicate_of: {
          project_id: "project-1",
          graph_id: "graph-1",
          source_id: "paper-1",
          title: "Earlier upload",
          workspace_path: "/g/project-1/graph-1",
        },
      },
    });
  });
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Sample",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });

  await page.goto("/papers");
  await page
    .getByLabel("Paper (PDF)")
    .setInputFiles({
      name: "paper.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 dup"),
    });

  const form = page.getByRole("form", { name: "Upload a paper" });
  await expect(form.getByText(/Already extracted as/)).toBeVisible();
  await expect(form.getByRole("link", { name: "Open existing workspace" })).toHaveAttribute(
    "href",
    "/g/project-1/graph-1",
  );
});

test("import from an arXiv ID extracts the download", async ({ page }) => {
  await page.route("**/api/v1/papers/import", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        source: "1706.03762v7",
        source_url: "https://arxiv.org/pdf/1706.03762v7",
        filename: "1706.03762v7.pdf",
        extraction: extractionPayload("Imported arXiv paper", "arxiv"),
      },
    });
  });
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Sample",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });

  await page.goto("/papers");
  const form = page.getByRole("form", { name: "Import a paper from a link" });
  await form.getByLabel("ArXiv ID, DOI, or URL").fill("1706.03762v7");
  await page.getByRole("button", { name: "Import and extract" }).click();

  const section = page.getByRole("region", { name: "Import a paper" });
  await expect(section.getByText(/Imported from /)).toContainText(
    "https://arxiv.org/pdf/1706.03762v7",
  );
  await expect(section.getByText("Imported arXiv paper")).toBeVisible();
});
