import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const graph = {
  schema_version: "1.0",
  project_id: "project-papers",
  graph_id: "graph-papers",
  version: 2,
  title: "AlphaFold paper",
  source_ids: ["paper-papers"],
  nodes: [
    {
      id: "input",
      kind: "input",
      label: "Sequence",
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

async function stubPapersHub(page: Page) {
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
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      json: {
        user_id: "user-1",
        email: "me@example.com",
        name: "Me",
        created_at: "2026-01-01T00:00:00+00:00",
      },
    });
  });
  await page.route("**/api/v1/users/me/papers", async (route) => {
    await route.fulfill({
      json: [
        {
          project_id: "project-papers",
          graph_id: "graph-papers",
          source_id: "paper-papers",
          title: "AlphaFold paper",
          created_at: "2026-01-02T00:00:00+00:00",
        },
      ],
    });
  });
}

test("login lands on papers with the library", async ({ page }) => {
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: "user-1",
          email: "me@example.com",
          name: "Me",
          created_at: "2026-01-01T00:00:00+00:00",
        },
        token: "test-token",
        expires_at: "2026-01-08T00:00:00+00:00",
      },
    });
  });
  await stubPapersHub(page);

  await page.goto("/login");
  await page.getByLabel("Email").fill("me@example.com");
  await page.getByLabel("Password").fill("correct-horse-9");
  await page.getByRole("form", { name: "Login form" }).getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL(/\/papers$/);
  const library = page.getByRole("region", { name: "My papers" });
  await expect(library.getByRole("link", { name: "AlphaFold paper" })).toHaveAttribute(
    "href",
    "/g/project-papers/graph-papers",
  );
});

test("logged-in home redirects to papers", async ({ page }) => {
  await page.addInitScript(
    "window.localStorage.setItem('bizora.auth.token', 'test-token');",
  );
  await stubPapersHub(page);

  await page.goto("/");
  await expect(page).toHaveURL(/\/papers$/);
  await expect(page.getByRole("link", { name: "AlphaFold paper" })).toBeVisible();
});

test("a library paper opens its workspace", async ({ page }) => {
  await page.addInitScript(
    "window.localStorage.setItem('bizora.auth.token', 'test-token');",
  );
  await stubPapersHub(page);
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/graphs/**/diff*", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-papers",
        graph_id: "graph-papers",
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

  await page.goto("/papers");
  await page.getByRole("link", { name: "AlphaFold paper" }).click();

  await expect(page).toHaveURL(/\/g\/project-papers\/graph-papers$/);
  await expect(page.getByRole("heading", { name: "AlphaFold paper" })).toBeVisible();
});
