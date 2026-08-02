import assert from "node:assert/strict";
import { test } from "node:test";

import {
  observeGitHubDelivery,
  parseGitHubObserveArgs
} from "../../services/report/a3_github_observe_cli.mjs";

test("A3 GitHub observer reads installation identity but does not infer tenant binding", async () => {
  const previous = process.env.GITHUB_TOKEN;
  process.env.GITHUB_TOKEN = "rt_secret";
  const calls = [];
  try {
    const result = await observeGitHubDelivery({
      repo: "acme/refund-agent",
      branch: "main",
      checkRunId: 9001,
      checkName: "A3 golden path release artifact",
      requiredCheckName: "A3 golden path release artifact",
      checkConclusion: "success",
      headSha: "candidate-abc123",
      expectedAppSlug: "releasefoundry-enterprise",
      expectedAppId: 12345,
      expectedInstallationAlias: "7001",
      checkedAt: "2026-07-13T01:00:00.000Z",
      fetchImpl: async (url, init) => {
        calls.push({ url, init });
        if (url.endsWith("/installation")) {
          return new Response(JSON.stringify({
            id: 7001,
            app_id: 12345,
            app_slug: "releasefoundry-enterprise",
            target_type: "Organization",
            repository_selection: "selected",
            permissions: { checks: "write" },
            events: ["check_run"],
            suspended_at: null,
            account: { login: "private-owner", email: "owner@example.com" }
          }), { status: 200 });
        }
        if (url.includes("/check-runs/")) {
          return new Response(JSON.stringify({
            id: 9001,
            name: "A3 golden path release artifact",
            status: "completed",
            conclusion: "success",
            head_sha: "candidate-abc123",
            app: { id: 12345, slug: "releasefoundry-enterprise", owner: { type: "Organization" } }
          }), { status: 200 });
        }
        if (url.includes("/protection/required_status_checks")) {
          return new Response(JSON.stringify({
            strict: true,
            contexts: [],
            checks: [{ context: "A3 golden path release artifact", app_id: 12345 }]
          }), { status: 200 });
        }
        throw new Error(`Unexpected URL: ${url}`);
      }
    });

    assert.equal(result.check_readback.readback_status, "readback_confirmed");
    assert.equal(result.required_check_proof.enforced, true);
    assert.equal(result.repository_installation_readback.repository_bound, true);
    assert.equal(result.repository_installation_readback.identity_matches, true);
    assert.equal(result.closure.repository_installation_readback, true);
    assert.equal(result.closure.repository_installation_identity_matches, true);
    assert.equal(result.closure.custom_tenant_github_app_proven, false);
    assert.equal(result.repository_installation_readback.calibration.tenant_binding_receipt_present, false);
    assert.equal(calls.length, 3);
    assert.doesNotMatch(JSON.stringify(result), /rt_secret|private-owner|owner@example\.com|authorization/i);
  } finally {
    if (previous === undefined) delete process.env.GITHUB_TOKEN;
    else process.env.GITHUB_TOKEN = previous;
  }
});

test("A3 GitHub observer parses installation calibration options without accepting a token value", () => {
  const options = parseGitHubObserveArgs([
    "--repo", "acme/refund-agent",
    "--expected-app-slug", "releasefoundry-enterprise",
    "--expected-app-id", "12345",
    "--expected-installation-alias", "7001",
    "--output-installation", "fixtures/install.json"
  ]);

  assert.equal(options.expectedAppSlug, "releasefoundry-enterprise");
  assert.equal(options.expectedAppId, 12345);
  assert.equal(options.expectedInstallationAlias, "7001");
  assert.equal(options.outputInstallation, "fixtures/install.json");
  assert.equal(Object.hasOwn(options, "token"), false);
});
