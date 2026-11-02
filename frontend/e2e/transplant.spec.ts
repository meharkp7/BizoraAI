import { expect, test } from "@playwright/test";

const graphs = [
  {
    project_id: "project-1",
    graph_id: "graph-1",
    version: 2,
    title: "Vision transformer",
    source_ids: ["paper-1"],
    node_count: 2,
    edge_count: 1,
    created_by: "test",
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    project_id: "project-2",
    graph_id: "graph-2",
    version: 1,
    title: "SRAM PUF",
    source_ids: ["paper-2"],
    node_count: 3,
    edge_count: 2,
    created_by: "test",
    created_at: "2026-01-01T00:00:00Z",
  },
];

const revision = {
  schema_version: "1.0",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  title: "Vision transformer",
  source_ids: ["paper-1"],
  nodes: [
    {
      id: "encoder",
      kind: "model",
      label: "Transformer encoder",
      description: null,
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [],
      provenance: "extracted",
      confidence: null,
    },
  ],
  edges: [],
  created_by: "test",
  parent_version: 1,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs", async (route) => {
    await route.fulfill({ json: graphs });
  });
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: revision });
  });
  await page.route("**/api/v1/graphs/**/transplant", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        project_id: "project-2",
        graph_id: "graph-2",
        version: 2,
        title: "Transplant 1 block from graph-1",
        added_node_ids: ["encoder"],
        renamed: {},
        copied_edge_count: 0,
        dropped_edge_count: 0,
      },
    });
  });
});

test("transplant moves source blocks into a new target revision", async ({ page }) => {
  await page.goto("/cross-paper");

  const list = page.getByRole("region", { name: "Graphs" });
  await list.getByRole("button", { name: "Add to tray" }).first().click();
  await list.getByRole("button", { name: "Add to tray" }).nth(1).click();

  await page.getByRole("tab", { name: "Transplant" }).click();
  await page.getByLabel("Source graph").selectOption("project-1::graph-1");
  await expect(page.getByText("Blocks from Vision transformer")).toBeVisible();
  await page.getByRole("checkbox", { name: /Transformer encoder/ }).check();
  await page.getByLabel("Target graph").selectOption("project-2::graph-2");
  await page.getByRole("button", { name: "Transplant" }).click();

  await expect(page.getByText("Transplant 1 block from graph-1")).toBeVisible();
  await expect(page.getByRole("link", { name: "graph-2 v2" })).toHaveAttribute(
    "href",
    "/g/project-2/graph-2",
  );
});
