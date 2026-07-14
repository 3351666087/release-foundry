import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const webappUrl = new URL("../../apps/webapp/", import.meta.url);
const expectedRoutes = [
  "api-reference-page.tsx",
  "billing-page.tsx",
  "case-page.tsx",
  "delivery-page.tsx",
  "login-page.tsx",
  "overview-page.tsx",
  "projects-page.tsx",
  "reports-page.tsx",
  "review-page.tsx",
  "runs-page.tsx",
  "team-page.tsx",
  "trust-page.tsx"
];

test("A3 webapp exposes the complete product workflow as typed routes", async () => {
  const [routesSource, routePageSource, pageFiles] = await Promise.all([
    readFile(new URL("lib/routes.ts", webappUrl), "utf8"),
    readFile(new URL("app/[section]/page.tsx", webappUrl), "utf8"),
    readdir(new URL("components/pages/", webappUrl))
  ]);

  for (const route of ["login", "overview", "projects", "runs", "case", "review", "reports", "delivery", "api-reference", "team", "billing", "trust"]) {
    assert.match(routesSource, new RegExp(`id: "${route}"`));
  }
  assert.deepEqual(pageFiles.filter((file) => file.endsWith("-page.tsx")).sort(), expectedRoutes);
  assert.match(routePageSource, /generateStaticParams/);
  assert.match(routePageSource, /dynamicParams = false/);
});

test("A3 webapp consumes A1 and A2 through the existing read-only dashboard API", async () => {
  const [apiSource, providerSource, overviewSource, caseSource, reviewSource] = await Promise.all([
    readFile(new URL("lib/api.ts", webappUrl), "utf8"),
    readFile(new URL("components/dashboard-provider.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/overview-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/case-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/review-page.tsx", webappUrl), "utf8")
  ]);

  assert.match(apiSource, /\/api\/a3\/dashboard/);
  assert.match(apiSource, /credentials:\s*"include"/);
  assert.doesNotMatch(apiSource, /headers:\s*\{\s*"x-a3-role"/);
  assert.match(apiSource, /run_fixture/);
  assert.match(apiSource, /grade_fixture/);
  assert.match(apiSource, /trusted_release_authority/);
  assert.match(providerSource, /fetchDashboard/);
  assert.match(overviewSource, /a1_a2_evidence_spine/);
  assert.match(overviewSource, /trustedReleaseAuthority/);
  assert.doesNotMatch(overviewSource, /releaseDecision\.includes\("block"\)/);
  assert.match(caseSource, /Trace timeline/);
  assert.match(caseSource, /Judge decisions/);
  assert.match(reviewSource, /Authoritative decision/);
  assert.match(reviewSource, /multimodal_review_queue/);
  assert.match(reviewSource, /Multimodal disagreement review/);
  assert.match(reviewSource, /can_change_release_decision/);
  assert.match(reviewSource, /operational_state/);
  assert.match(reviewSource, /assignment_active_count/);
  assert.match(reviewSource, /Human assignment/);
  assert.match(reviewSource, /产品不会据此改写分数、风险或发布决定/);
});

test("A3 webapp keeps auth and commercial writes explicitly fail-closed", async () => {
  const [loginSource, reviewSource, reportsSource, billingSource, teamSource, apiReferenceSource, i18nSource, authApiSource] = await Promise.all([
    readFile(new URL("components/pages/login-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/review-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/reports-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/billing-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/team-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/api-reference-page.tsx", webappUrl), "utf8"),
    readFile(new URL("lib/i18n.tsx", webappUrl), "utf8"),
    readFile(new URL("lib/auth-api.ts", webappUrl), "utf8")
  ]);

  assert.match(loginSource, /READ-ONLY DEMO IDENTITY/);
  assert.match(loginSource, /does not create an account/);
  assert.match(loginSource, /authContractCapabilities/);
  assert.match(loginSource, /oauthInitialLogin/);
  assert.match(loginSource, /requestEmailVerification/);
  assert.match(loginSource, /contractBlocker/);
  assert.match(reviewSource, /disabled/);
  assert.match(reportsSource, /hosted report service/);
  assert.match(billingSource, /live payment backend/);
  assert.match(teamSource, /hosted auth/);
  assert.match(apiReferenceSource, /productCopy\(zh \? endpoint\.description\.zh/);
  assert.match(apiReferenceSource, /productCopy\(endpoint\.source, zh\)/);
  assert.match(apiReferenceSource, /productCopy\(zh \? note\.zh : note\.en, zh\)/);
  assert.doesNotMatch(i18nSource, /common\.loading[^\n]+A1\/A2/);
  assert.doesNotMatch(authApiSource, /"[^"]*\bA1\b[^"]*"/);
  assert.doesNotMatch([loginSource, reviewSource, reportsSource, billingSource, teamSource].join("\n"), /ASHR_API_KEY|sk-[A-Za-z0-9]/);
});

test("deployment receipt UI displays authoritative readbacks without exposing the internal verifier", async () => {
  const [deliverySource, inboxSource] = await Promise.all([
    readFile(new URL("components/pages/delivery-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/deployment-receipt-inbox.tsx", webappUrl), "utf8")
  ]);

  assert.match(deliverySource, /deployment_acceptance_projection/);
  assert.match(deliverySource, /projection=\{deploymentAcceptanceProjection\}/);
  assert.match(inboxSource, /authoritative_readbacks/);
  assert.match(inboxSource, /production_verification/);
  assert.match(inboxSource, /SERVER-ONLY READBACK/);
  assert.match(inboxSource, /There is no browser verification control/);
  assert.doesNotMatch(inboxSource, /\/internal\/a3\/deployment\/receipts/);
  assert.doesNotMatch(inboxSource, /postDeploymentReceiptVerification|verifyDeploymentReceipt/);
});

test("self-host sandbox UI consumes A1 evidence without presenting it as production proof", async () => {
  const [deliverySource, sandboxSource] = await Promise.all([
    readFile(new URL("components/pages/delivery-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/self-host-sandbox-panel.tsx", webappUrl), "utf8")
  ]);

  assert.match(deliverySource, /SelfHostSandboxPanel/);
  assert.match(deliverySource, /acceptancePassed/);
  assert.match(deliverySource, /acceptanceTotal/);
  assert.match(sandboxSource, /\/api\/a3\/deployment\/sandbox-calibration/);
  assert.match(sandboxSource, /credentials: "include"/);
  for (const state of ["loading", "empty", "partial", "failed", "denied", "ready"]) {
    assert.match(sandboxSource, new RegExp(`"${state}"`));
  }
  assert.match(sandboxSource, /这不是生产部署证明/);
  assert.match(sandboxSource, /不会改变部署验收/);
  assert.match(sandboxSource, /不会重算权威裁决/);
  assert.match(sandboxSource, /production_gaps/);
  assert.match(sandboxSource, /postgres_qualification/);
  assert.match(sandboxSource, /PostgreSQL 五层租户隔离已验证/);
  assert.match(sandboxSource, /target_class/);
  assert.match(sandboxSource, /cross_scope_write_denied/);
  assert.match(sandboxSource, /仍为 8\/17/);
  assert.match(sandboxSource, /deployment:read/);
  assert.doesNotMatch(sandboxSource, /\/internal\/a3\/deployment|x-a3-role|ASHR_API_KEY/);
});

test("A3 webapp visual source enforces the Signal-Form safety constraints", async () => {
  const [css, runsSource, ignoreSource, packageSource] = await Promise.all([
    readFile(new URL("app/globals.css", webappUrl), "utf8"),
    readFile(new URL("components/pages/runs-page.tsx", webappUrl), "utf8"),
    readFile(new URL(".gitignore", webappUrl), "utf8"),
    readFile(new URL("package.json", webappUrl), "utf8")
  ]);

  assert.doesNotMatch(css, /gradient\(/i);
  assert.doesNotMatch(css, /letter-spacing:\s*-/i);
  assert.match(css, /counter-increment: a3-section/);
  assert.match(css, /@media \(max-width: 560px\)/);
  assert.match(runsSource, /pageSize = 10/);
  assert.match(runsSource, /table-pagination/);
  assert.match(ignoreSource, /\.next\//);
  assert.match(ignoreSource, /out\//);
  assert.match(packageSource, /"check": "npm run typecheck && npm run build"/);
});
