import { expect, test } from "@playwright/test";

const run = {
  run_id: "run-ok",
  config: {
    experiment_id: "exp-1",
    project_id: "project-1",
    graph_id: "graph-1",
    graph_version: 2,
    adapter_id: "bizora.deterministic-test",
    adapter_version: "0.1.0",
    dataset_id: "dataset-1",
    dataset_revision: "rev-1",
    seed: 7,
    epochs: 1,
    batch_size: 8,
    learning_rate: 0.001,
    split: { train: 0.8, validation: 0.1, test: 0.1 },
    code_revision: "abcdef1234567",
    max_runtime_seconds: 60,
    max_gpu_count: 0,
    network_access: false,
  },
  state: "succeeded",
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:01:00Z",
  finished_at: "2026-01-01T00:02:00Z",
  error: null,
};

const usageSummary = {
  generated_at: "2026-11-02T10:00:00+00:00",
  currency: "USD",
  estimated: true,
  days: [
    {
      date: "2026-11-02",
      calls: 3,
      input_tokens: 1200,
      output_tokens: 300,
      cost_usd_estimated: 0.0081,
      unmetered_calls: 1,
    },
  ],
  totals: {
    calls: 3,
    input_tokens: 1200,
    output_tokens: 300,
    cost_usd_estimated: 0.0081,
    unmetered_calls: 1,
  },
  caps: { daily_cap_usd: 25.0, run_cap_usd: 5.0, max_runs_per_day: 50 },
};

test("profile shows estimated spend and caps", async ({ page }) => {
  await page.addInitScript(
    "window.localStorage.setItem('bizora.auth.token', 'test-token');",
  );
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
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/usage/summary*", async (route) => {
    await route.fulfill({ json: usageSummary });
  });

  await page.goto("/profile");
  const section = page.getByRole("region", { name: "Usage and spend" });
  await expect(section.getByText("$0.01 · 1 unmetered").first()).toBeVisible();
  await expect(section.getByText("$25.00")).toBeVisible();
});

test("runs list shows each run's estimated cost", async ({ page }) => {
  await page.route("**/api/v1/experiments/runs*", async (route) => {
    await route.fulfill({ json: [run] });
  });
  await page.route("**/api/v1/usage/runs*", async (route) => {
    await route.fulfill({
      json: [
        {
          run_id: "run-ok",
          project_id: "project-1",
          graph_id: "graph-1",
          calls: 2,
          input_tokens: 5000,
          output_tokens: 1000,
          cost_usd_estimated: 0.03,
          unmetered: false,
          last_used_at: "2026-11-01T09:00:00+00:00",
        },
      ],
    });
  });

  await page.goto("/g/project-1/graph-1/runs");
  await expect(page.getByText("run-ok")).toBeVisible();
  await expect(page.getByText("$0.03 estimated")).toBeVisible();
});
