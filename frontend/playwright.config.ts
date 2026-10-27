import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke coverage for the Phase D shell. Specs stub the API at the network
 * layer so the harness runs without a backend; real-backend end-to-end
 * coverage against a seeded API arrives in Phase I.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
