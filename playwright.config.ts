import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.A3_DASHBOARD_E2E_PORT || 4173);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  metadata: {
    appUnderTest: "apps/dashboard",
    a3Surface: "Product Console / Report Center / Release Evidence"
  },
  timeout: 45_000,
  expect: {
    timeout: 10_000
  },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  outputDir: "docs/screenshots/playwright-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: {
    command: `node tests/e2e/static-dashboard-server.mjs --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 10_000
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
