import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const webappUrl = new URL("../../apps/webapp/", import.meta.url);
const expectedRoutes = [
  "api-reference-page.tsx",
  "billing-page.tsx",
  "case-page.tsx",
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

  for (const route of ["login", "overview", "projects", "runs", "case", "review", "reports", "api-reference", "team", "billing", "trust"]) {
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
  assert.match(apiSource, /x-a3-role/);
  assert.match(apiSource, /run_fixture/);
  assert.match(apiSource, /grade_fixture/);
  assert.match(providerSource, /fetchDashboard/);
  assert.match(overviewSource, /a1_a2_evidence_spine/);
  assert.match(caseSource, /Trace timeline/);
  assert.match(caseSource, /Judge decisions/);
  assert.match(reviewSource, /A2 release authority/);
});

test("A3 webapp keeps auth and commercial writes explicitly fail-closed", async () => {
  const [loginSource, reviewSource, reportsSource, billingSource, teamSource] = await Promise.all([
    readFile(new URL("components/pages/login-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/review-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/reports-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/billing-page.tsx", webappUrl), "utf8"),
    readFile(new URL("components/pages/team-page.tsx", webappUrl), "utf8")
  ]);

  assert.match(loginSource, /READ-ONLY DEMO IDENTITY/);
  assert.match(loginSource, /does not create an account/);
  assert.match(loginSource, /startOAuth/);
  assert.match(loginSource, /requestEmailVerification/);
  assert.match(loginSource, /contractBlocker/);
  assert.match(reviewSource, /disabled/);
  assert.match(reportsSource, /hosted report service/);
  assert.match(billingSource, /live payment backend/);
  assert.match(teamSource, /hosted auth/);
  assert.doesNotMatch([loginSource, reviewSource, reportsSource, billingSource, teamSource].join("\n"), /ASHR_API_KEY|sk-[A-Za-z0-9]/);
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
