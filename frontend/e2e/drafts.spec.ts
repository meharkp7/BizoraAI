import { expect, test, type Page } from "@playwright/test";

const graph = {
  schema_version: "1.0",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  title: "Vision transformer",
  source_ids: ["paper-1"],
  nodes: [
    {
      id: "input",
      kind: "input",
      label: "Image",
      description: null,
      config: {},
      input_shape: null,
      output_shape: [null, 768],
      evidence: [],
      provenance: "verified",
      confidence: 0.99,
    },
    {
      id: "encoder",
      kind: "model",
      label: "Transformer encoder",
      description: "Patch embedding plus transformer blocks.",
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [],
      provenance: "verified",
      confidence: 0.95,
    },
  ],
  edges: [],
  created_by: "test",
  parent_version: 1,
};

const history = [
  {
    version: 1,
    parent_version: null,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    version: 2,
    parent_version: 1,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-02T00:00:00Z",
  },
];

const emptyDiff = {
  project_id: "project-1",
  graph_id: "graph-1",
  base_version: 1,
  target_version: 2,
  added_nodes: [],
  removed_nodes: [],
  changed_nodes: [],
  added_edges: [],
  removed_edges: [],
  changed_edges: [],
};

async function mockWorkspace(page: Page) {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    const segments = route.request().url().split("/");
    const version = Number(segments[segments.length - 1] ?? "2") || 2;
    await route.fulfill({
      json: { ...graph, version, parent_version: version > 1 ? version - 1 : null },
    });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({ json: emptyDiff });
  });
}

test("scenario draft stages a canvas edit and promotes it", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/graphs/**/patches", async (route) => {
    await route.fulfill({
      status: 201,
      json: { ...graph, version: 3, parent_version: 2 },
    });
  });

  await page.goto("/g/project-1/graph-1?v=2");
  const panel = page.getByRole("region", { name: "Scenario drafts" });
  await panel.getByLabel("Draft name").fill("Fewer layers");
  await panel.getByRole("button", { name: "Draft from v2" }).click();
  await expect(page.getByText(/Staging into Fewer layers \(0 ops\)/)).toBeVisible();

  const nodes = page.getByRole("list", { name: "Graph nodes" });
  await nodes.getByRole("button", { name: /Transformer encoder/ }).click();
  const inspector = page.getByRole("region", { name: "Inspector" });
  await inspector.getByLabel("Node configuration JSON").fill('{"layers": 6}');
  await inspector.getByRole("button", { name: "Apply configuration" }).click();

  await expect(page.getByText(/Staging into Fewer layers \(1 op\)/)).toBeVisible();
  await expect(
    panel.getByText("Update encoder configuration (encoder)"),
  ).toBeVisible();

  await panel.getByRole("button", { name: "Promote to revision" }).click();
  await expect(page).toHaveURL(/v=3/);
});

test("scenario draft discards without touching the server", async ({ page }) => {
  await mockWorkspace(page);
  let patchCalls = 0;
  await page.route("**/api/v1/graphs/**/patches", async (route) => {
    patchCalls += 1;
    await route.fulfill({ status: 201, json: { ...graph, version: 3 } });
  });

  await page.goto("/g/project-1/graph-1?v=2");
  const panel = page.getByRole("region", { name: "Scenario drafts" });
  await panel.getByRole("button", { name: "Draft from v2" }).click();
  await expect(page.getByText(/Staging into Scenario 1/)).toBeVisible();

  await panel.getByRole("button", { name: "Discard" }).click();
  await panel.getByRole("button", { name: "Confirm discard" }).click();

  await expect(panel.getByText("No drafts for this graph yet.")).toBeVisible();
  expect(patchCalls).toBe(0);
});
