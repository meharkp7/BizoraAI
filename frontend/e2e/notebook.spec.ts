import { expect, test, type Page } from "@playwright/test";

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

const runs = [
  {
    run_id: "run-ok",
    config: {
      experiment_id: "exp-1",
      project_id: "project-1",
      graph_id: "graph-1",
      graph_version: 2,
      adapter_id: "bizora.deterministic-test",
      adapter_version: "0.1.0",
      dataset_id: "d",
      dataset_revision: "v1",
      seed: 7,
      code_revision: "r",
    },
    state: "succeeded",
    created_at: "2026-01-03T00:00:00Z",
    started_at: "2026-01-03T00:00:00Z",
    finished_at: "2026-01-03T00:00:01Z",
    error: null,
  },
];

async function mockNotebook(page: Page) {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
  await page.route("**/api/v1/experiments/runs", async (route) => {
    await route.fulfill({ json: runs });
  });
  await page.route("**/api/v1/experiments/runs/*/metrics", async (route) => {
    await route.fulfill({
      json: [
        {
          metric_id: "metric-1",
          run_id: "run-ok",
          name: "accuracy",
          value: 0.92,
          result_kind: "measured",
        },
      ],
    });
  });
  await page.route("**/api/v1/papers/*/notes", async (route) => {
    await route.fulfill({ json: [] });
  });
}

test("notebook assembles revisions, runs, and notes", async ({ page }) => {
  await mockNotebook(page);

  await page.goto("/g/project-1/graph-1/notebook");
  await expect(page.getByRole("heading", { name: "Notebook" })).toBeVisible();

  const historySection = page.getByRole("region", { name: "Revision history" });
  await expect(historySection.getByText("v2")).toBeVisible();
  await expect(historySection.getByText("v1")).toBeVisible();

  const runsSection = page.getByRole("region", { name: "Experiment runs" });
  await expect(runsSection.getByText("run-ok")).toBeVisible();
  await expect(runsSection.getByText("accuracy = 0.92")).toBeVisible();
});

test("workspace navigation reaches the notebook", async ({ page }) => {
  await mockNotebook(page);
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({
      json: {
        schema_version: "1.0",
        project_id: "project-1",
        graph_id: "graph-1",
        version: 2,
        title: "Vision transformer",
        source_ids: ["paper-1"],
        nodes: [],
        edges: [],
        created_by: "test",
        parent_version: 1,
      },
    });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({
      json: {
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
      },
    });
  });

  await page.goto("/g/project-1/graph-1");
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("link", {
    name: "Notebook",
  }).click();

  await expect(page).toHaveURL(/\/notebook$/);
  await expect(page.getByRole("heading", { name: "Notebook" })).toBeVisible();
});
