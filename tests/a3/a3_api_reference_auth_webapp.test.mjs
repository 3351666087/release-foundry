import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("API Reference is a typed route grounded in A1, A2, and A3 contracts", async () => {
  const [routes, app, page, reference] = await Promise.all([
    source("apps/webapp/lib/routes.ts"),
    source("apps/webapp/components/product-app.tsx"),
    source("apps/webapp/components/pages/api-reference-page.tsx"),
    source("apps/webapp/lib/api-reference.ts")
  ]);

  assert.match(routes, /id: "api-reference"/);
  assert.match(app, /"api-reference": ApiReferencePage/);
  assert.match(page, /apiEndpoints/);
  assert.match(page, /Search APIs/);
  assert.match(page, /Request example/);
  assert.match(page, /Response example/);
  assert.match(reference, /a1Sha: "ac960bd"/);
  assert.match(reference, /a2Sha: "58fe876"/);
  assert.match(page, /A1 Capture · A2 Judge · A3 Operate/);
  assert.match(reference, /\/v1\/identity-verification\/challenges/);
  assert.match(reference, /\/internal\/judge\/case/);
  assert.match(reference, /\/api\/a3\/dashboard/);
  assert.match(reference, /status: "blocked"/);
});

test("A3 auth adapter calls A1 without taking custody of provider secrets", async () => {
  const auth = await source("apps/webapp/lib/auth-api.ts");

  assert.match(auth, /NEXT_PUBLIC_A1_API_BASE_URL/);
  assert.match(auth, /NEXT_PUBLIC_A1_PROJECT_ID/);
  assert.match(auth, /NEXT_PUBLIC_A1_TENANT_ID/);
  assert.match(auth, /\/oauth\/\$\{provider\}\/start/);
  assert.match(auth, /\/v1\/identity-verification\/challenges/);
  assert.match(auth, /\/v1\/identity-verification\/verify/);
  assert.match(auth, /credentials: "include"/);
  assert.match(auth, /accounts\.google\.com/);
  assert.match(auth, /github\.com/);
  assert.match(auth, /url\.protocol !== "https:"/);
  assert.match(auth, /cache: "no-store"/);
  assert.doesNotMatch(auth, /client[_A-Za-z]*secret|ASHR_API_KEY|SMTP_AUTH|Bearer\s+[A-Za-z0-9]/i);
  assert.doesNotMatch(auth, /localStorage|sessionStorage|console\.(?:log|debug|info|warn|error)/);
});

test("login and registration disclose upstream capability gaps instead of faking success", async () => {
  const login = await source("apps/webapp/components/pages/login-page.tsx");

  assert.match(login, /Continue with Google/);
  assert.match(login, /Continue with GitHub/);
  assert.match(login, /Send verification code/);
  assert.match(login, /completeEmailVerification/);
  assert.match(login, /!challengeId/);
  assert.match(login, /current callback returns JSON/);
  assert.match(login, /current A1 SMTP sender still sends plain text/);
  assert.match(login, /This preview does not create an account or store email or credentials/);
  assert.doesNotMatch(login, /localStorage|sessionStorage|document\.cookie|console\./);
});

test("verification email handoff is public-safe and email-client compatible", async () => {
  const [html, textTemplate, changeRequest] = await Promise.all([
    source("apps/webapp/emails/verification-email.html"),
    source("apps/webapp/emails/verification-email.txt"),
    source("docs/a3/a1_identity_verification_contract_change_request_2026_07_11.md")
  ]);

  assert.match(html, /\{\{VERIFICATION_CODE\}\}/);
  assert.match(html, /\{\{VERIFICATION_URL\}\}/);
  assert.match(html, /role="presentation"/);
  assert.match(html, /API key 或 OAuth token/);
  assert.match(textTemplate, /\{\{EXPIRES_IN_MINUTES\}\}/);
  assert.doesNotMatch(html, /<script|<form|<img|https?:\/\/(?!\{\{VERIFICATION_URL)/i);
  assert.doesNotMatch(html, /on(?:click|load|error)=/i);
  assert.match(changeRequest, /public start response remains indistinguishable/);
  assert.match(changeRequest, /Same-email implicit account merging remains forbidden/);
  assert.match(changeRequest, /A3 never fabricates a verified account/);
});

test("redacted auth snapshot records current peer SHAs and blockers without secrets", async () => {
  const fixture = JSON.parse(await source("fixtures/a3/auth/a1_a2_auth_contract_snapshot.redacted.json"));
  assert.equal(fixture.schema_version, "a3.auth_contract_snapshot.v1");
  assert.equal(fixture.main.contained_by_a3_branch, true);
  assert.equal(fixture.a1.sha, "ac960bdaf9d3ca2afe27b5e07e4625bdc1f824f2");
  assert.equal(fixture.a1.pull_request_state, "open_draft");
  assert.equal(fixture.a1.calibration.production_ready, false);
  assert.equal(fixture.a2.sha, "58fe8762de982b2b5d285de9ae4a438f120ec318");
  assert.equal(fixture.a3.oauth_provider_secrets_owned, false);
  assert.equal(fixture.known_blockers.length, 3);
  assert.equal(fixture.safety.api_key_read, false);
  assert.equal(fixture.safety.real_email_recorded, false);
  const serialized = JSON.stringify(fixture);
  const forbidden = new RegExp([
    "s" + "k-",
    "gh" + "p_",
    "github" + "_pat_",
    "Bearer" + "\\s",
    "BEGIN PRIVATE" + " KEY",
    "@gmail\\.com",
    "@qq\\.com"
  ].join("|"), "i");
  assert.doesNotMatch(serialized, forbidden);
});
