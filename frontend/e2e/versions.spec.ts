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

test("version history marks the current revision and views older ones", async ({
  page,
}) => {
  await mockWorkspace(page);

  await page.goto("/g/project-1/graph-1?v=2");
  const panel = page.getByRole("region", { name: "Version history" });
  await expect(panel.getByText("v2")).toBeVisible();
  await expect(panel.getByText("current")).toBeVisible();
  await expect(panel.getByText("v1")).toBeVisible();

  await panel.getByRole("button", { name: "View" }).click();
  await expect(page).toHaveURL(/v=1/);
});

test("restore confirms before appending a new head revision", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/graphs/**/revisions/1/restore", async (route) => {
    await route.fulfill({
      status: 201,
      json: { ...graph, version: 3, parent_version: 2, created_by: "workspace-ui" },
    });
  });

  await page.goto("/g/project-1/graph-1?v=2");
  const panel = page.getByRole("region", { name: "Version history" });
  await panel.getByRole("button", { name: "Restore" }).click();
  await expect(
    panel.getByText("Restore v1 as a new revision?"),
  ).toBeVisible();

  await panel.getByRole("button", { name: "Confirm restore" }).click();
  await expect(page).toHaveURL(/v=3/);
});

test("compare sends an older revision to the diff view", async ({ page }) => {
  await mockWorkspace(page);

  await page.goto("/g/project-1/graph-1?v=2");
  const panel = page.getByRole("region", { name: "Version history" });
  await panel.getByRole("button", { name: "Compare" }).click();

  const diff = page.getByRole("region", { name: "Revision comparison" });
  await expect(diff.getByLabel("Base")).toHaveValue("1");
  await expect(diff.getByLabel("Target")).toHaveValue("2");
});
