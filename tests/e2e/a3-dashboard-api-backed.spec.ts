import { expect, type Locator, type Page, test } from "@playwright/test";

const apiBackedPath = "/apps/dashboard/index.html?source=api-mock";

test.describe("A3 API-backed dashboard E2E", () => {
  test("loads dashboard through the local A3 API and keeps A1/A2/SaaS contracts visible", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    const dashboardResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/dashboard")
      && response.request().method() === "GET"
    ));

    await page.goto(apiBackedPath);
    await expect((await dashboardResponse).status()).toBe(200);

    await expect(page.locator("#data-source")).toContainText("API-backed A1/A2 mock fixture");
    await expect(page.locator("#metric-cases")).toHaveText("32");
    await expect(page.locator("#metric-runs")).toHaveText("1");

    const runtime = section(page, "#saas-runtime");
    await expect(runtime).toContainText("Dashboard data is API-backed");
    await expect(runtime).toContainText("API surfaces");
    await expect(runtime).toContainText("POST /api/a3/import/a1-run-result");
    await expect(runtime).toContainText("POST /api/a3/import/a2-grade-result");
    await expect(runtime).toContainText("DB tables");
    await expect(runtime).toContainText("Usage meters");

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("SaaS Admin Console");
    await expect(admin).toContainText("Login");
    await expect(admin).toContainText("Team");
    await expect(admin).toContainText("API Keys");
    await expect(admin).toContainText("Trust");
    await expect(admin).toContainText("no real cloud write");
    await expect(admin).toContainText("A1/A2 Compatibility");

    const reviewerWorkflow = section(page, "#reviewer-workflow");
    await expect(reviewerWorkflow).toContainText("Reviewer Workflow");
    await expect(reviewerWorkflow).toContainText("A1 trace");
    await expect(reviewerWorkflow).toContainText("A2 judge evidence");

    expect(consoleErrors, "API-backed dashboard should not emit browser console errors").toEqual([]);
  });

  test("creates and revokes a hosted report through the local A3 API", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await expect(page.locator("#data-source")).toContainText("API-backed A1/A2 mock fixture");

    const shareResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/reports/share")
      && response.request().method() === "POST"
    ));
    await page.locator("[data-share-report]").first().click();
    await expect((await shareResponse).status()).toBe(201);
    await expect(page.locator("#share-report-status")).toHaveText("shareable");
    await expect(page.locator("#share-report-detail")).toContainText("sha256");

    const reportCenter = page.locator("#report-center");
    await expect(reportCenter).toContainText("Hosted Reports");
    await expect(reportCenter).toContainText("/r/[REDACTED_TOKEN]");

    const revokeResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/reports/")
      && response.url().includes("/revoke")
      && response.request().method() === "POST"
    ));
    await reportCenter.getByRole("button", { name: "Revoke" }).first().click();
    await expect((await revokeResponse).status()).toBe(200);
    await expect(page.locator("#share-report-status")).toHaveText("revoked");
    await expect(page.locator("#share-report-detail")).toContainText("dashboard_revoke");
    await expect(reportCenter).toContainText("revoked");

    expect(consoleErrors, "hosted report lifecycle should not emit browser console errors").toEqual([]);
  });
});

function section(page: Page, selector: string): Locator {
  return page.locator(selector);
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  return errors;
}
