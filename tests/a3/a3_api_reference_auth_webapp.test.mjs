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
  assert.match(reference, /mainSha: "ccf6ce5"/);
  assert.match(reference, /schemaVersion: "a3\.api_reference\.v18"/);
  assert.match(reference, /a1Sha: "c784163"/);
  assert.match(reference, /a2Sha: "8cd1d4f"/);
  assert.match(reference, /a1SourceState: "merged_to_main"/);
  assert.match(reference, /a2SourceState: "merged_to_main"/);
  assert.match(page, /UPSTREAM A1 INTEGRATION/);
  assert.match(page, /a2RequiredScope\.map/);
  assert.match(page, /运行平台 · 评测策略 · 产品工作流/);
  assert.match(reference, /\/v1\/identity\/registration\/email\/begin/);
  assert.match(reference, /\/v1\/identity\/registration\/email\/complete/);
  assert.match(reference, /\/v1\/identity\/login\/email\/begin/);
  assert.match(reference, /\/v1\/identity\/login\/email\/complete/);
  assert.match(reference, /browser-sessions\/refresh/);
  assert.match(reference, /\/internal\/judge\/case/);
  assert.match(reference, /\/api\/a3\/import\/a2-multimodal-comparison/);
  assert.match(reference, /\/api\/a3\/import\/a2-multimodal-repeat-stability/);
  assert.match(reference, /\/api\/a3\/review\/multimodal-repeat-stability/);
  assert.match(reference, /\/api\/a3\/import\/a2-multimodal-provider-readiness/);
  assert.match(reference, /\/api\/a3\/providers\/multimodal-readiness/);
  assert.match(reference, /\/api\/a3\/review\/multimodal-queue/);
  assert.match(reference, /multimodal-queue\/\{queueId\}\/assignment/);
  assert.match(reference, /multimodal-queue\/\{queueId\}\/evidence-requests/);
  assert.match(reference, /evidence-requests\/\{requestId\}\/submissions/);
  assert.match(reference, /evidence-requests\/\{requestId\}\/review/);
  assert.match(reference, /a2\.multimodal_cross_provider_comparison\.v1/);
  assert.match(reference, /a2\.multimodal_cross_provider_comparison\.v3/);
  assert.match(reference, /a2\.multimodal_three_way_comparison\.v2/);
  assert.match(reference, /a2\.multimodal_multi_repeat_comparison\.v1/);
  assert.match(reference, /a2\.multimodal_multi_repeat_comparison\.v2/);
  assert.match(reference, /a2\.multimodal_public_summary\.round52\.v1/);
  assert.match(reference, /a3\.multimodal_release_readiness\.v1/);
  assert.match(reference, /a3\.multimodal_release_case_evidence\.v1/);
  assert.match(reference, /hash_only_no_signed_url/);
  assert.match(reference, /round51-attack-safety-guidance-conflict-01/);
  assert.match(reference, /a3\.multimodal_repeat_stability\.v1/);
  assert.match(reference, /a3\.a2_multimodal_provider_readiness_intake\.v1/);
  assert.match(reference, /a3\.multimodal_provider_readiness\.v1/);
  assert.match(reference, /blocked_provider_readiness/);
  assert.match(reference, /a3\.multimodal_review_queue\.v1/);
  assert.match(reference, /bb3bcfe/);
  assert.match(reference, /850b39a/);
  assert.match(reference, /6a985b8/);
  assert.match(reference, /566a13d/);
  assert.match(reference, /IdentityCredentialLinkCoordinator/);
  assert.match(reference, /a1AtomicCredentialLinkRouteLifecycle: "proposed"/);
  assert.match(reference, /a1AtomicCredentialLinkClientCallable: false/);
  assert.match(reference, /a2CurrentRemoteSha: "850b39a"/);
  assert.match(reference, /a1CredentialLinkReplayRetentionDays: 30/);
  assert.match(reference, /a1CredentialLinkReadinessRouteAvailable: false/);
  assert.match(reference, /aggregate_comparisons/);
  assert.match(reference, /receipt conservation/);
  assert.match(reference, /release_decision_changed: false/);
  assert.match(reference, /a3\.multimodal_review_assignment_receipt\.v1/);
  assert.match(reference, /a3\.multimodal_review_assignment_packet\.v1/);
  assert.match(reference, /a3\.multimodal_review_evidence_request_receipt\.v1/);
  assert.match(reference, /authoritative_human_disposition_recorded: false/);
  assert.match(reference, /audit_archive_signature_verified: false/);
  assert.match(reference, /action: "claim"/);
  assert.match(reference, /expected_version: 0/);
  assert.match(reference, /\/api\/a3\/dashboard/);
  assert.match(reference, /a3\.deployment_handoff\.v1/);
  assert.match(reference, /a3\.deployment_receipt_inbox\.v1/);
  assert.match(reference, /a3\.deployment_acceptance_projection\.v1/);
  assert.match(reference, /a3\.deployment_receipt_authoritative_readback\.v1/);
  assert.match(reference, /a3\.self_host_sandbox_calibration\.v1/);
  assert.match(reference, /\/api\/a3\/deployment\/sandbox-calibration/);
  assert.match(reference, /deployment_acceptance_mutated: false/);
  assert.match(reference, /a2_decision_recomputed: false/);
  assert.match(reference, /\/api\/a3\/deployment\/receipts/);
  assert.match(reference, /\/internal\/a3\/deployment\/receipts\/\{receipt_id\}\/verify/);
  assert.match(reference, /expected_version/);
  assert.match(reference, /production_verified: false/);
  assert.match(reference, /integrity_invalid/);
  assert.match(reference, /current_release_authorized/);
  assert.match(reference, /a2\.evidence_snapshot\.v1/);
  assert.match(reference, /a2\.decision_ledger\.v1/);
  assert.match(reference, /status: "blocked"/);
});

test("A3 auth adapter calls A1 without taking custody of provider secrets", async () => {
  const auth = await source("apps/webapp/lib/auth-api.ts");

  assert.match(auth, /NEXT_PUBLIC_A1_API_BASE_URL/);
  assert.match(auth, /NEXT_PUBLIC_A1_PROJECT_ID/);
  assert.match(auth, /NEXT_PUBLIC_A1_TENANT_ID/);
  assert.match(auth, /startOAuthAccountLinking/);
  assert.doesNotMatch(auth, /export async function startOAuth\(/);
  assert.match(auth, /\/oauth\/\$\{provider\}\/start/);
  assert.match(auth, /\/v1\/identity\/\$\{purpose\}\/email\/begin/);
  assert.match(auth, /\/v1\/identity\/\$\{purpose\}\/email\/complete/);
  assert.match(auth, /challenge_id/);
  assert.match(auth, /intent_id/);
  assert.match(auth, /proof/);
  assert.match(auth, /redirect: "follow"/);
  assert.match(auth, /finalUrl\.pathname !== "\/console"/);
  assert.match(auth, /browser-sessions\/refresh/);
  assert.match(auth, /identity_session_same_origin_required/);
  assert.match(auth, /oauthInitialLogin: false/);
  assert.match(auth, /sourceState: "merged_to_a3"/);
  assert.match(auth, /emailBrowserCompletion: true/);
  assert.match(auth, /emailLoginSessionCookie: true/);
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

  assert.match(login, /Google sign-in pending/);
  assert.match(login, /GitHub sign-in pending/);
  assert.match(login, /Current route is account linking only/);
  assert.match(login, /Send registration code/);
  assert.match(login, /Send sign-in code/);
  assert.match(login, /completeEmailRegistration/);
  assert.match(login, /completeEmailLogin/);
  assert.match(login, /!challengeId/);
  assert.match(login, /Google\/GitHub first login remains disabled/);
  assert.match(login, /identity service currently sends plain text/);
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
  assert.equal(fixture.schema_version, "a3.auth_contract_snapshot.v4");
  assert.equal(fixture.main.sha, "ccf6ce57890aaceabcb627c14d2e078674bd50ad");
  assert.equal(fixture.main.a1_a2_integration_sha, "7dd14d7b154ad86bd3bfedacbf4c3e03796170ce");
  assert.equal(fixture.main.contained_by_a3_branch, true);
  assert.equal(fixture.a1.sha, "780e94fc9de29563e70cb41a5855a679780601fc");
  assert.equal(fixture.a1.pull_request_state, "merged_into_a3_branch");
  assert.equal(fixture.a1.merged_to_main, false);
  assert.equal(fixture.a1.calibration.production_ready, false);
  assert.equal(fixture.a1.capabilities.oauth_account_linking, "implemented");
  assert.equal(fixture.a1.capabilities.verification_challenge_start, "implemented");
  assert.equal(fixture.a1.capabilities.verification_completion, "implemented_with_browser_intent");
  assert.equal(fixture.a1.capabilities.email_registration, "implemented");
  assert.equal(fixture.a1.capabilities.email_login, "implemented");
  assert.equal(fixture.a1.capabilities.oauth_initial_login, "unavailable");
  assert.equal(fixture.a2.sha, "8cd1d4f1cb72e73ae7ead5d3218b4ae963a31a81");
  assert.equal(fixture.a2.source_state, "merged_to_main");
  assert.equal(fixture.a1.calibration.browser_session_lifecycle, "implemented_and_tested");
  assert.equal(fixture.a1.calibration.oauth_initial_login, "not_implemented");
  assert.equal(fixture.a2.trusted_spine.evidence_snapshot_schema, "a2.evidence_snapshot.v1");
  assert.equal(fixture.a2.trusted_spine.decision_ledger_schema, "a2.decision_ledger.v1");
  assert.deepEqual(fixture.a2.trusted_spine.required_scope_fields, [
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id"
  ]);
  assert.equal(fixture.a2.trusted_spine.scope_complete, true);
  assert.deepEqual(fixture.a2.trusted_spine.validation_errors, []);
  assert.equal(fixture.a2.trusted_spine.direct_a1_run_result_validation, true);
  assert.equal(fixture.a2.trusted_spine.release_ready, false);
  assert.equal(fixture.a2.trusted_spine.a3_may_recompute_grade, false);
  assert.equal(fixture.a3.oauth_provider_secrets_owned, false);
  assert.equal(fixture.known_blockers.length, 2);
  assert.equal(fixture.known_blockers.some((blocker) => blocker.id === "a1_auth_not_in_main"), false);
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
