import { readFileSync } from "node:fs";

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

  test("records SaaS Admin guardrail requests without real cloud mutation", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await expect(page.locator("#data-source")).toContainText("API-backed A1/A2 mock fixture");

    const admin = section(page, "#saas-admin");
    await admin.locator("[data-admin-action-select]").selectOption("invite_teammate");
    await expect(admin.locator("[data-admin-action-plan]")).toContainText("plan_only");
    await expect(admin.locator("[data-admin-action-plan]")).toContainText("no real cloud write");

    const submitResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/admin/actions/submit")
      && response.request().method() === "POST"
    ));
    await admin.locator("[data-admin-action-submit]").click();
    await expect((await submitResponse).status()).toBe(202);

    await expect(admin).toContainText("Admin Action Requests");
    await expect(admin).toContainText("invite_teammate");
    await expect(admin).toContainText("recorded_plan_only");
    await expect(admin).toContainText("no real cloud write");
    await expect(admin).not.toContainText("owner@example.com");
    await expect(admin).not.toContainText("teammate@example.com");

    expect(consoleErrors, "admin guardrail flow should not emit browser console errors").toEqual([]);
  });

  test("records reviewer waiver and approval receipts and renders durable review records", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await expect(page.locator("#data-source")).toContainText("API-backed A1/A2 mock fixture");

    const waiver = loadFixture("fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
    const approval = loadFixture("fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");

    const waiverResponse = await page.request.post(apiUrl(page, "/api/a3/review/waivers?source=mock"), {
      headers: {
        "x-a3-role": "reviewer"
      },
      data: {
        waiver,
        generated_at: "2026-07-07T12:00:00.000Z"
      }
    });
    await expect(waiverResponse.status()).toBe(202);
    const waiverReceipt = await waiverResponse.json();
    expect(waiverReceipt.status).toBe("valid_exceptional_waiver");
    expect(waiverReceipt.accepted).toBe(true);

    const approvalResponse = await page.request.post(apiUrl(page, "/api/a3/review/approvals?source=mock"), {
      headers: {
        "x-a3-role": "reviewer"
      },
      data: {
        approval,
        waiver,
        generated_at: "2026-07-07T12:00:00.000Z"
      }
    });
    await expect(approvalResponse.status()).toBe(202);
    const approvalReceipt = await approvalResponse.json();
    expect(approvalReceipt.status).toBe("valid_exception_approval");
    expect(approvalReceipt.accepted).toBe(true);

    await page.reload();
    const records = section(page, "#review-workflow-records");
    await expect(records).toContainText("Durable Review Records");
    await expect(records).toContainText("Records");
    await expect(records).toContainText("Waivers");
    await expect(records).toContainText("Approvals");
    await expect(records).toContainText("valid_exceptional_waiver");
    await expect(records).toContainText("valid_exception_approval");
    await expect(records).toContainText("hash_sealed");

    const workflowResponse = await page.request.get(apiUrl(page, "/api/a3/review/workflow?source=mock"));
    await expect(workflowResponse.status()).toBe(200);
    const workflow = await workflowResponse.json();
    expect(workflow.record_count).toBeGreaterThanOrEqual(2);
    expect(workflow.durable_storage_ready).toBe(true);
    expect(JSON.stringify(workflow)).not.toContain("owner@example.com");

    expect(consoleErrors, "review workflow receipt flow should not emit browser console errors").toEqual([]);
  });

  test("renders denied hosted report pages without leaking case evidence", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);

    const shareResponse = await page.request.post(apiUrl(page, "/api/a3/reports/share?source=mock"), {
      headers: {
        "x-a3-role": "reviewer"
      },
      data: {
        source: "mock",
        title: "A3 Round 4 denied-state report",
        visibility: "private_link",
        created_by: "round4-e2e"
      }
    });
    await expect(shareResponse.status()).toBe(201);
    const report = await shareResponse.json();

    const sharePath = report.share_url_path;
    expect(sharePath).toMatch(/^\/r\//);
    await page.goto(apiUrl(page, sharePath));
    await expect(page.locator("body")).toContainText("A3 Round 4 denied-state report");
    await expect(page.locator("body")).toContainText("Case Evidence");

    const revokeResponse = await page.request.post(apiUrl(page, `/api/a3/reports/${encodeURIComponent(report.report_id)}/revoke?source=mock`), {
      headers: {
        "x-a3-role": "owner"
      },
      data: {
        reason: "round4_denied_state_e2e",
        revoked_by: "round4-e2e"
      }
    });
    await expect(revokeResponse.status()).toBe(200);

    const revokedResponse = await page.goto(apiUrl(page, sharePath));
    expect(revokedResponse?.status()).toBe(410);
    await expect(page.locator("body")).toContainText("A3 report is not available");
    await expect(page.locator("body")).toContainText("revoked");
    await expect(page.locator("body")).not.toContainText("Case Evidence");
    await expect(page.locator("body")).not.toContainText("Expected");
    await expect(page.locator("body")).not.toContainText("Actual");

    const missingResponse = await page.goto(apiUrl(page, "/r/missing-share-token-round4"));
    expect(missingResponse?.status()).toBe(404);
    await expect(page.locator("body")).toContainText("A3 report is not available");
    await expect(page.locator("body")).not.toContainText("Case Evidence");

    const unexpectedConsoleErrors = consoleErrors.filter((message) => (
      !message.includes("status of 410")
      && !message.includes("status of 404")
    ));
    expect(unexpectedConsoleErrors, "hosted denied-state flow should not emit unexpected browser console errors").toEqual([]);
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

function loadFixture(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function apiUrl(page: Page, path: string): string {
  return new URL(path, page.url()).toString();
}
