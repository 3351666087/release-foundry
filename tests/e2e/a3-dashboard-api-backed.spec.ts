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
    const schemaDriftResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/a1-a2/schema-drift")
      && response.request().method() === "GET"
    ));

    await page.goto(apiBackedPath);
    await expect((await dashboardResponse).status()).toBe(200);
    await expect((await schemaDriftResponse).status()).toBe(200);

    await waitForApiDashboard(page);
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
    await expect(admin).toContainText("Cloud workspace shell");
    await expect(admin).toContainText("Governance Overview");
    await expect(admin).toContainText("Cloud workspace shell");
    await expect(admin).toContainText("Governance Overview");
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

    const contractRadar = section(page, "#schema-drift-radar");
    await expect(contractRadar).toContainText("A1/A2 Contract Radar");
    await expect(contractRadar).toContainText("compatible");
    await expect(contractRadar).toContainText("a1_run_result");
    await expect(contractRadar).toContainText("raw schema payload not embedded");

    expect(consoleErrors, "API-backed dashboard should not emit browser console errors").toEqual([]);
  });

  test("renders Billing Migration Readiness evidence from the local A3 API", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);

    await page.goto(apiBackedPath);
    const migrationPanel = section(page, "#billing-migration-readiness");
    await expect(migrationPanel).toContainText("Billing Migration Readiness");
    await expect(migrationPanel).toContainText("Waiting for A1 billing ledger migration");

    const migrationResponse = await page.request.get(apiUrl(page, "/api/a3/billing/migration-readiness?source=mock"), {
      headers: {
        "x-a3-role": "auditor"
      }
    });
    await expect(migrationResponse.status()).toBe(200);
    const migration = await migrationResponse.json();
    expect(migration.schema_version).toBe("a3.billing_migration_readiness.v1");
    expect(migration.summary.status).toBe("read_only_migration_contract_ready");
    expect(migration.summary.ready_for_live_customer_billing).toBe(false);
    expect(migration.safety.env_local_read).toBe(false);
    expect(migration.safety.real_api_called_by_a3).toBe(false);
    expect(migration.safety.real_payment_provider_called).toBe(false);
    expect(migration.api_contract.some((route: { route?: string }) => route.route === "GET /api/a3/billing/readiness")).toBe(true);
    expect(migration.db_contract.tables.some((table: { name?: string }) => table.name === "billing_provider_events")).toBe(true);
    expect(migration.event_contract.ledger_event_types).toContain("usage_reconciled");
    expect(JSON.stringify(migration)).not.toMatch(/Bearer|sk-|ghp_|github_pat_|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);

    await expect(page.locator("body")).not.toContainText("owner@example.com");
    await expect(page.locator("body")).not.toContainText("teammate@example.com");

    await page.screenshot({
      path: "docs/screenshots/a3-billing-migration-readiness-api-backed-2026-07-09.png",
      fullPage: true
    });

    expect(consoleErrors, "billing migration readiness dashboard evidence should not emit browser console errors").toEqual([]);
  });

  test("shows review filters, share governance, and cloud summary strip", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const reviewer = section(page, "#reviewer-workflow");
    await expect(reviewer).toContainText("Filter records");
    await expect(reviewer).toContainText("reviewer");
    await expect(reviewer).toContainText("owner");

    const reportCenter = page.locator("#report-center");
    await expect(reportCenter).toContainText("Audience Filters");
    await expect(reportCenter).toContainText("Workspace Groups");
    await expect(reportCenter).toContainText("Environment Groups");
    await expect(reportCenter).toContainText("External Publish Blockers");

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("Cloud Summary Strip");
    await expect(admin).toContainText("Auth");
    await expect(admin).toContainText("Trust");

    await page.screenshot({
      path: "docs/screenshots/a3-review-governance-cloudstrip-2026-07-10.png",
      fullPage: true
    });

    expect(consoleErrors, "review filters and cloud summary surfaces should not emit browser console errors").toEqual([]);
  });

  test("creates and revokes a hosted report through the local A3 API", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const shareResponse = page.waitForResponse((response) => (
      response.url().includes("/api/a3/reports/share")
      && response.request().method() === "POST"
    ));
    await page.locator("[data-share-report]").first().click();
    await expect((await shareResponse).status()).toBe(201);
    await expect(page.locator("#share-report-status")).toHaveText("shareable");
    await expect(page.locator("#share-report-detail")).toContainText("sha256");

    const reportCenter = page.locator("#report-center");
    await expect(reportCenter).toContainText("Artifact Registry");
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
    await waitForApiDashboard(page);

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
    await waitForApiDashboard(page);

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

    expect(consoleErrors, "review workflow receipts should not emit browser console errors").toEqual([]);
  });

  test("shows hosted report scope and commercial admin enterprise controls together", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const reportCenter = page.locator("#report-center");
    await expect(reportCenter).toContainText("Artifact Registry");
    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("Cloud workspace shell");
    await expect(admin).toContainText("Governance Overview");
    await expect(admin).toContainText("Procurement / Sign-Off Posture");
    await expect(admin).toContainText("Usage Escalation");
    await expect(admin).toContainText("Collections / Invoice Escalation");
    await expect(admin).toContainText("Workspace Action Readiness");
    await expect(admin).toContainText("owner_plus_reviewer");
    await expect(admin).toContainText("blocked_until_hosted_auth");
    await expect(section(page, "#review-workflow-records")).toContainText("Report Share Readiness");
    await expect(admin).toContainText("Separation Of Duties");
    await expect(admin).toContainText("Workspace / Environment Control");

    const enterprise = section(page, "#enterprise-readiness");
    await expect(enterprise).toContainText("Hosted Buyer Readiness");

    await page.screenshot({
      path: "docs/screenshots/a3-commercial-escalation-console-api-backed-2026-07-10.png",
      fullPage: true
    });

    expect(consoleErrors, "scope and commercial governance surfaces should not emit browser console errors").toEqual([]);
  });

  test("shows export audience governance and enterprise decision packets in the API-backed console", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("Export / Audience Governance");
    await expect(admin).toContainText("customer_external");
    await expect(admin).toContainText("reviewer_signoff");
    await expect(admin).toContainText("executive_summary");
    await expect(admin).toContainText("blocked");

    const enterprise = section(page, "#enterprise-readiness");
    await expect(enterprise).toContainText("Decision Packets");
    await expect(enterprise).toContainText("Reviewer packet");
    await expect(enterprise).toContainText("Executive packet");
    await expect(enterprise).toContainText("Customer packet");
    await expect(enterprise).toContainText("Customer blocked");

    await page.screenshot({
      path: "docs/screenshots/a3-export-governance-enterprise-packets-api-backed-2026-07-10.png",
      fullPage: true
    });

    expect(consoleErrors, "export governance and enterprise decision packets should not emit browser console errors").toEqual([]);
  });

  test("shows release publish chain continuity in live ops control plane", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const liveOps = section(page, "#live-ops-control-plane");
    await expect(liveOps).toContainText("Release publish chain");
    await expect(liveOps).toContainText("reviewer_records");
    await expect(liveOps).toContainText("github_check_publish");
    await expect(liveOps).toContainText("github_pr_comment");
    await expect(liveOps).toContainText("hosted_report_share");
    await expect(liveOps).toContainText("usage_visibility");
    await expect(liveOps).toContainText("billing_visibility");
    await expect(liveOps).toContainText("Commercial sign-off");
    await expect(liveOps).toContainText("Required roles");
    await expect(liveOps).toContainText("Customer external");
    await expect(liveOps).toContainText("Sign-off blockers");
    await expect(liveOps).not.toContainText("[object HTMLDivElement]");

    await page.screenshot({
      path: "docs/screenshots/a3-live-publish-chain-api-backed-2026-07-10.png",
      fullPage: true
    });
    await liveOps.screenshot({
      path: "docs/screenshots/a3-commercial-signoff-summary-api-backed-2026-07-10.png"
    });

    expect(consoleErrors, "release publish chain should not emit browser console errors").toEqual([]);
  });

  test("shows trust publish blockers and customer-safe artifact posture", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto(apiBackedPath);
    await waitForApiDashboard(page);

    const admin = section(page, "#saas-admin");
    await expect(admin).toContainText("Trust Center");
    await expect(admin).toContainText("Blocked reason");
    await expect(admin).toContainText("publish blocker:");
    await expect(admin).toContainText("customer-safe artifact:");
    await expect(admin).toContainText("hosted trust publishing service");

    await page.screenshot({
      path: "docs/screenshots/a3-trust-blockers-api-backed-2026-07-10.png",
      fullPage: true
    });

    expect(consoleErrors, "trust blockers should not emit browser console errors").toEqual([]);
  });
});

async function waitForApiDashboard(page: Page) {
  await expect.poll(async () => await page.locator("#data-source").textContent(), { timeout: 15000 }).toContain("API-backed A1/A2 mock fixture");
}

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
