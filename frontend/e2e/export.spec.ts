import { expect, test } from "@playwright/test";

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

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/projects/*/graphs/*/export", async (route) => {
    await route.fulfill({
      json: {
        bundle_version: "1.0",
        exported_at: "2026-11-02T00:00:00+00:00",
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        graph,
        memory: [],
      },
    });
  });
});

test("workspace exports the graph bundle", async ({ page }) => {
  await page.goto("/g/project-1/graph-1?v=2");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export bundle" }).click();
  const file = await download;

  expect(file.suggestedFilename()).toBe("project-1-graph-1-v2.json");
});
