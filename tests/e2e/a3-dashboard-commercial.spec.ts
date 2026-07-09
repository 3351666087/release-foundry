import { expect, type Locator, type Page, test } from "@playwright/test";

const officialDemoPath = "/apps/dashboard/index.html?source=p3-official-demo";

test.describe("A3 dashboard commercial E2E", () => {
  test("renders real dashboard content from the official-demo source", async ({ page }) => {
    await openDashboard(page);

    await expect(page.locator("#data-source")).toContainText("P3 official Ashr demo dataset 884 / run 11926");
    await expect(page.locator("#metric-runs")).toHaveText("1");
    await expect(page.locator("#metric-cases")).toHaveText("5");
    await expect(page.locator("#metric-pass-rate")).toHaveText("40%");
    await expect(page.locator("#metric-media")).toHaveText("5");

    await expect(section(page, "#runs")).toContainText("happy_path_text_valid_booking");
    await expect(section(page, "#detail")).toContainText("Expected");
    await expect(section(page, "#detail")).toContainText("Actual");
    await expect(section(page, "#timeline")).toContainText("Trace Timeline");
    await expect(section(page, "#clusters")).toContainText("Failure Clusters");

    await page.screenshot({
      path: "docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png",
      fullPage: true
    });
  });

  test("covers Product Console, Report Center, Release Evidence, Review, and Admin surfaces", async ({ page }) => {
    await openDashboard(page);

    const productConsole = section(page, "#product-console");
    await expect(productConsole).toContainText("Product Console");
    await expect(productConsole).toContainText("Onboarding Flow");
    await expect(productConsole).toContainText("Project Console");
    await expect(productConsole).toContainText("Audit Log");
    await expect(productConsole).toContainText("Commercial Readiness");

    const reportCenter = section(page, "#operations").filter({ hasText: "Report Center" });
    await expect(reportCenter).toContainText("JSON");
    await expect(reportCenter).toContainText("Markdown");
    await expect(reportCenter).toContainText("Release Evidence");
    await expect(reportCenter).toContainText("Artifact Registry");

    const releaseEvidence = section(page, "#release-evidence");
    await expect(releaseEvidence).toContainText("Release Evidence");
    await expect(releaseEvidence).toContainText("Check readback");
    await expect(releaseEvidence).toContainText("PR comment readback");
    await expect(releaseEvidence).toContainText("Audit bundle");
    await expect(releaseEvidence).toContainText("tokens not included");

    const reviewerWorkflow = section(page, "#reviewer-workflow");
    await expect(reviewerWorkflow).toContainText("Reviewer Workflow");
    await expect(reviewerWorkflow).toContainText("A1 trace");
    await expect(reviewerWorkflow).toContainText("A2 judge evidence");
    await expect(reviewerWorkflow).toContainText("Durable Review Records");

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("SaaS Admin Console");
    await expect(admin).toContainText("Login");
    await expect(admin).toContainText("RBAC Matrix");
    await expect(admin).toContainText("Usage");
    await expect(admin).toContainText("API Key Lifecycle");
    await expect(admin).toContainText("Trust Center");
    await expect(admin).toContainText("Cloud Action Plan");
    await expect(admin).toContainText("secret value never rendered");
  });

  test("keeps API, DB, tenant, RBAC, usage, audit, and A1/A2 contracts visible", async ({ page }) => {
    await openDashboard(page);

    const runtime = section(page, "#saas-runtime");
    await expect(runtime).toContainText("API surfaces");
    await expect(runtime).toContainText("GET /api/a3/dashboard");
    await expect(runtime).toContainText("POST /api/a3/import/a1-run-result");
    await expect(runtime).toContainText("POST /api/a3/import/a2-grade-result");
    await expect(runtime).toContainText("DB tables");
    await expect(runtime).toContainText("team_members");
    await expect(runtime).toContainText("GET /api/a3/artifacts/registry");
    await expect(runtime).toContainText("Usage meters");

    const productConsole = section(page, "#product-console");
    await expect(productConsole).toContainText("org-local");
    await expect(productConsole).toContainText("project-local");

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("RBAC");
    await expect(admin).toContainText("A1/A2 Compatibility");
    await expect(admin).toContainText("no real cloud write");
    await expect(admin).toContainText("redacted identity");

    const enterprise = section(page, "#enterprise-readiness");
    await expect(enterprise).toContainText("Enterprise Readiness");
    await expect(enterprise).toContainText("A1/A2 Compatibility");
    await expect(enterprise).toContainText("A1 traces");
    await expect(enterprise).toContainText("A2 judges");

    const contractRadar = section(page, "#schema-drift-radar");
    await expect(contractRadar).toContainText("A1/A2 Contract Radar");
    await expect(contractRadar).toContainText("not_attached");
    await expect(contractRadar).toContainText("raw schema payload not embedded");
  });

  test("supports dashboard interactions without leaving the real page shell", async ({ page }) => {
    await openDashboard(page);

    await page.locator("#filter-status").selectOption("failed");
    await expect(page.locator("#visible-count")).toContainText("3 visible");
    await expect(section(page, "#triage-queue")).toContainText("major");

    await page.locator("#source-select").selectOption("raw-a2");
    await expect(page.locator("#data-source")).toContainText("Raw A2 single-case fixture");
    await expect(page.locator("#metric-cases")).toHaveText("1");
    await expect(section(page, "#release-gate")).toContainText("Release Gate");
    await expect(section(page, "#report-preview")).toContainText("Report Preview");
  });
});

async function openDashboard(page: Page) {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  await page.goto(officialDemoPath);
  await expect(page.locator("#data-source")).not.toContainText("Loading local fixtures");
  await expect(page.locator("h1")).toHaveText("A3 Product Console");
  expect(consoleErrors, "dashboard should not emit browser console errors while loading").toEqual([]);
}

function section(page: Page, selector: string): Locator {
  return page.locator(selector);
}
