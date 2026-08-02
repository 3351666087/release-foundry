import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createA3ApiHandler,
  resolveA3DirectStartRouteAccessMode,
  startA3ApiServer
} from "../../services/report/a3_api_server.mjs";
import { A3_RBAC_ROLES } from "../../services/report/a3_auth_rbac_boundary.mjs";
import {
  createFixtureBackedA3Store,
  createMemoryA3Store
} from "../../services/report/a3_store.mjs";

const SCOPE = Object.freeze({
  organization_id: "org-local",
  tenant_id: "tenant-local",
  workspace_id: "workspace-local",
  project_id: "project-local",
  environment_id: "staging"
});

test("direct server startup defaults to hosted enforcement regardless of NODE_ENV", () => {
  assert.equal(resolveA3DirectStartRouteAccessMode({}), "hosted_enforced");
  assert.equal(resolveA3DirectStartRouteAccessMode({ NODE_ENV: "development" }), "hosted_enforced");
  assert.equal(resolveA3DirectStartRouteAccessMode({ A3_ROUTE_ACCESS_MODE: "demo_contract" }), "demo_contract");
});

test("A3 defaults to hosted enforcement and denies forged browser authority without A1 principal resolution", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({ store }, async (url) => {
    const health = await fetch(`${url}/api/a3/health`);
    assert.equal((await health.json()).route_access_mode, "hosted_enforced");
    const response = await fetch(`${url}/api/a3/dashboard?source=mock&role=owner`, {
      headers: {
        "x-a3-role": "owner",
        "x-a3-actor-id": "forged-owner",
        authorization: `Bearer ${"x".repeat(32)}`
      }
    });
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_unauthorized.v1",
      error: "authentication_required"
    });
  });

  const serialized = JSON.stringify(store.exportState());
  assert.doesNotMatch(serialized, /forged-owner|Bearer\s+x|x-a3-role/i);
  assert.equal(store.exportState().auditEvents.some((event) => event.event_type === "route_access.denied"), true);
});

test("hosted A3 consumes a server-verified A1 principal and preserves the A2 block decision", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const cookieSecret = "session-cookie-must-not-persist";
  let resolverCalls = 0;
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    async resolveTrustedPrincipal(request) {
      resolverCalls += 1;
      assert.match(request.headers.cookie || "", /__Host-releasefoundry_session=/);
      return trustedPrincipal({ role: "auditor" });
    }
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/dashboard?source=mock`, {
      headers: {
        cookie: `__Host-releasefoundry_session=${cookieSecret}`,
        "x-a3-role": "owner"
      }
    });
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.summary.totalCases, 32);
    assert.equal(payload.a1_a2_evidence_spine.release_decision, "block");
    assert.equal(payload.a1_a2_evidence_spine.status, "blocked");
    assert.equal(payload.a1_a2_evidence_spine.safety.a1_or_a2_semantics_mutated, false);
  });

  assert.equal(resolverCalls, 1);
  const state = store.exportState();
  assert.equal(state.auditEvents.some((event) => event.event_type === "route_access.allowed"), true);
  assert.equal(state.eventOutbox.some((event) => event.event_type === "route_access.allowed"), true);
  assert.doesNotMatch(JSON.stringify(state), new RegExp(cookieSecret));
});

test("hosted A3 ignores forged role headers and returns a sanitized 403", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "viewer" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/billing/readiness?source=mock`, {
      headers: { "x-a3-role": "owner", "x-a3-actor-id": "forged-billing-owner" }
    });
    assert.equal(response.status, 403);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_forbidden.v1",
      error: "access_denied"
    });
  });
  assert.doesNotMatch(JSON.stringify(store.exportState()), /forged-billing-owner/);
});

test("hosted A3 rejects cross-scope query and nested body assertions before handler execution", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const queryMismatch = await fetch(`${url}/api/a3/dashboard?source=mock&project_id=project-other`);
    assert.equal(queryMismatch.status, 403);

    const nestedMismatch = await fetch(`${url}/api/a3/reports/share?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        title: "must not persist",
        report: { project_id: "project-other" },
        later_matching_scope: { project_id: SCOPE.project_id }
      })
    });
    assert.equal(nestedMismatch.status, 403);
    assert.equal((await store.listReports({ source: "mock" })).length, 0);
  });
  assert.doesNotMatch(JSON.stringify(store.exportState()), /project-other|must not persist/);
});

test("hosted A3 auth context comes from the trusted principal rather than query or headers", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "viewer" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/auth/context?role=owner&actor_id=owner%40example.test`, {
      headers: { "x-a3-role": "owner" }
    });
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.auth_context.role, "viewer");
    assert.equal(payload.auth_context.auth_state, "hosted_session");
    assert.equal(payload.auth_context.credential_source, "a1_trusted_principal");
    assert.equal(payload.auth_context.tenant_scope.project_id, SCOPE.project_id);
    assert.doesNotMatch(JSON.stringify(payload), /owner@example\.test/);
  });
});

test("hosted A3 fails closed when access audit persistence is unavailable", async () => {
  let dashboardRead = false;
  const store = {
    storage_mode: "external-test",
    async getDashboardSnapshot() {
      dashboardRead = true;
      return {};
    }
  };
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/dashboard`);
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.route_access_unavailable.v1",
      error: "authorization_audit_unavailable",
      message: "The authorization service is temporarily unavailable."
    });
  });
  assert.equal(dashboardRead, false);
});

test("health and token-scoped report access remain distinct public routes", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({ store, routeAccessMode: "hosted_enforced" }, async (url) => {
    const health = await fetch(`${url}/api/a3/health`);
    assert.equal(health.status, 200);
    const healthPayload = await health.json();
    assert.equal(healthPayload.route_access_mode, "hosted_enforced");
    assert.equal(healthPayload.hosted_identity_resolver_configured, false);
    assert.equal(healthPayload.production_auth_claimed, false);

    const shared = await fetch(`${url}/r/not-a-real-share-token`);
    assert.notEqual(shared.status, 401);
    assert.equal(shared.status, 404);
  });
});

test("hosted A3 requires a per-request principal resolver and rejects a static principal object", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    trustedPrincipal: trustedPrincipal()
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/dashboard?source=mock`);
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_unauthorized.v1",
      error: "authentication_required"
    });
  });
});

test("hosted A3 persists a metadata-only denial for an unregistered route", async () => {
  const store = createMemoryA3Store({ storageMode: "memory" });
  await withServer({ store, routeAccessMode: "hosted_enforced" }, async (url) => {
    const response = await fetch(`${url}/api/a3/not-registered/private-resource`);
    assert.equal(response.status, 403);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_forbidden.v1",
      error: "access_denied"
    });
  });

  const event = store.exportState().auditEvents.find((item) => item.resource_id === "unregistered_route");
  assert.ok(event);
  assert.equal(event.event_type, "route_access.denied");
  assert.equal(event.payload_inline, false);
});

test("hosted protected writes audit malformed JSON and preserve 400/401/403 precedence", async () => {
  const store = createMemoryA3Store({ storageMode: "memory" });
  const bodySecret = `sk-${"m".repeat(32)}`;
  const bearerSecret = `bearer-${"n".repeat(32)}`;
  const cookieSecret = `cookie-${"p".repeat(32)}`;
  const privateEmail = `malformed-owner${String.fromCharCode(64)}example.test`;
  const malformedBody = `{"api_key":"${bodySecret}","email":"${privateEmail}"`;

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/reports/share?source=body-secret-must-not-be-source`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${bearerSecret}`,
        cookie: `__Host-releasefoundry_session=${cookieSecret}`,
        "x-request-id": "request-malformed-owner"
      },
      body: malformedBody
    });
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_bad_request.v1",
      error: "invalid_json"
    });
  });

  await withServer({ store, routeAccessMode: "hosted_enforced" }, async (url) => {
    const response = await fetch(`${url}/api/a3/reports/share`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: malformedBody
    });
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_unauthorized.v1",
      error: "authentication_required"
    });
  });

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "viewer" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/reports/share`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: malformedBody
    });
    assert.equal(response.status, 403);
    assert.deepEqual(await response.json(), {
      schema_version: "a3.sanitized_forbidden.v1",
      error: "access_denied"
    });
  });

  const state = store.exportState();
  const malformedEvent = state.auditEvents.find((item) => item.decision === "denied_malformed_json");
  assert.ok(malformedEvent);
  assert.equal(malformedEvent.http_status, 400);
  assert.equal(malformedEvent.resource_id, "share_report");
  assert.equal(malformedEvent.source, "hosted-access");
  assert.equal(malformedEvent.payload_inline, false);
  assert.equal(malformedEvent.redaction_status, "metadata_only");
  assert.equal(malformedEvent.safety.raw_secret_values_allowed, false);
  assert.equal(state.auditEvents.some((item) => item.http_status === 401), true);
  assert.equal(state.auditEvents.some((item) => item.http_status === 403), true);

  const serialized = JSON.stringify(state);
  for (const sensitiveValue of [bodySecret, bearerSecret, cookieSecret, privateEmail, malformedBody, "body-secret-must-not-be-source"]) {
    assert.equal(serialized.includes(sensitiveValue), false, `${sensitiveValue} must not persist`);
  }
});

test("hosted authentication and RBAC denial happen before a protected body is consumed", async () => {
  for (const testCase of [
    { name: "missing principal", expectedStatus: 401, expectedError: "authentication_required" },
    {
      name: "viewer without share permission",
      expectedStatus: 403,
      expectedError: "access_denied",
      resolveTrustedPrincipal: async () => trustedPrincipal({ role: "viewer" })
    }
  ]) {
    const store = createMemoryA3Store({ storageMode: "memory" });
    let bodyRead = false;
    let responseStatus = null;
    let responseBody = "";
    const handler = createA3ApiHandler({
      store,
      routeAccessMode: "hosted_enforced",
      ...(testCase.resolveTrustedPrincipal
        ? { resolveTrustedPrincipal: testCase.resolveTrustedPrincipal }
        : {})
    });
    const request = {
      method: "POST",
      url: "/api/a3/reports/share",
      headers: { "content-type": "application/json" },
      async *[Symbol.asyncIterator]() {
        bodyRead = true;
        throw new Error("protected body must not be consumed before denial");
      }
    };
    const response = {
      writeHead(status) {
        responseStatus = status;
      },
      end(body) {
        responseBody = body || "";
      }
    };

    await handler(request, response);

    assert.equal(responseStatus, testCase.expectedStatus, testCase.name);
    assert.equal(JSON.parse(responseBody).error, testCase.expectedError, testCase.name);
    assert.equal(bodyRead, false, testCase.name);
    assert.equal(store.exportState().auditEvents.some((item) => item.http_status === testCase.expectedStatus), true);
    assert.doesNotMatch(JSON.stringify(store.exportState()), /protected body must not be consumed/);
  }
});

test("hosted request bodies enforce media type, object shape, and byte limits", async () => {
  const store = createMemoryA3Store({ storageMode: "memory" });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const wrongMedia = await fetch(`${url}/api/a3/reports/share`, {
      method: "POST",
      headers: { "content-type": "text/plain" },
      body: "{}"
    });
    assert.equal(wrongMedia.status, 415);
    assert.equal((await wrongMedia.json()).error, "unsupported_media_type");

    for (const invalidShape of ["null", "[]", "42", "\"text\""]) {
      const response = await fetch(`${url}/api/a3/reports/share`, {
        method: "POST",
        headers: { "content-type": "application/json; charset=utf-8" },
        body: invalidShape
      });
      assert.equal(response.status, 422);
      assert.equal((await response.json()).error, "invalid_json_shape");
    }
  });

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    maxJsonBodyBytes: 32,
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/reports/share`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "x".repeat(64) })
    });
    assert.equal(response.status, 413);
    assert.equal((await response.json()).error, "payload_too_large");
  });

  const state = store.exportState();
  assert.equal(state.auditEvents.some((item) => item.request_body_state === "unsupported_media_type"), true);
  assert.equal(state.auditEvents.filter((item) => item.request_body_state === "invalid_json_shape").length, 4);
  assert.equal(state.auditEvents.some((item) => item.request_body_state === "payload_too_large"), true);
  assert.ok(state.auditEvents.every((item) => item.payload_inline === false));
});

test("hosted request body read deadline returns an audited sanitized 408", async () => {
  const store = createMemoryA3Store({ storageMode: "memory" });
  let iteratorClosed = false;
  let responseStatus = null;
  let responseBody = "";
  const handler = createA3ApiHandler({
    store,
    routeAccessMode: "hosted_enforced",
    requestBodyReadTimeoutMs: 10,
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  });
  const request = {
    method: "POST",
    url: "/api/a3/reports/share",
    headers: { "content-type": "application/json" },
    [Symbol.asyncIterator]() {
      return {
        next: () => new Promise(() => {}),
        return: async () => {
          iteratorClosed = true;
          return { done: true };
        }
      };
    }
  };
  const response = {
    writeHead(status) {
      responseStatus = status;
    },
    end(body) {
      responseBody = body || "";
    }
  };

  await handler(request, response);

  assert.equal(responseStatus, 408);
  assert.equal(JSON.parse(responseBody).error, "request_timeout");
  assert.equal(iteratorClosed, true);
  const event = store.exportState().auditEvents.find((item) => item.request_body_state === "body_read_timeout");
  assert.ok(event);
  assert.equal(event.http_status, 408);
  assert.equal(event.payload_inline, false);
});

test("protected OPTIONS requests are route-matched, authorized, and audited before 204", async () => {
  const allowedStore = createMemoryA3Store({ storageMode: "memory" });
  const privateOrigin = "https://private-console.example.test";
  await withServer({
    store: allowedStore,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/reports/share`, {
      method: "OPTIONS",
      headers: {
        origin: privateOrigin,
        "access-control-request-method": "POST"
      }
    });
    assert.equal(response.status, 204);
    assert.equal(await response.text(), "");
  });

  const allowedEvent = allowedStore.exportState().auditEvents.find((item) => item.resource_id === "share_report");
  assert.ok(allowedEvent);
  assert.equal(allowedEvent.event_type, "route_access.allowed");
  assert.equal(allowedEvent.transport_method, "OPTIONS");
  assert.equal(allowedEvent.preflight_for_method, "POST");
  assert.equal(allowedEvent.payload_inline, false);
  assert.equal(JSON.stringify(allowedStore.exportState()).includes(privateOrigin), false);

  const deniedStore = createMemoryA3Store({ storageMode: "memory" });
  await withServer({ store: deniedStore, routeAccessMode: "hosted_enforced" }, async (url) => {
    const protectedResponse = await fetch(`${url}/api/a3/reports/share`, {
      method: "OPTIONS",
      headers: { "access-control-request-method": "POST" }
    });
    assert.equal(protectedResponse.status, 401);

    const unregisteredResponse = await fetch(`${url}/api/a3/not-registered`, {
      method: "OPTIONS",
      headers: { "access-control-request-method": "POST" }
    });
    assert.equal(unregisteredResponse.status, 403);

    const invalidMethodResponse = await fetch(`${url}/api/a3/reports/share`, {
      method: "OPTIONS",
      headers: { "access-control-request-method": "TRACE" }
    });
    assert.equal(invalidMethodResponse.status, 403);

    const publicHealth = await fetch(`${url}/api/a3/health`, {
      method: "OPTIONS",
      headers: { "access-control-request-method": "GET" }
    });
    assert.equal(publicHealth.status, 204);
  });

  const deniedEvents = deniedStore.exportState().auditEvents;
  assert.equal(deniedEvents.some((item) => item.http_status === 401 && item.transport_method === "OPTIONS"), true);
  assert.equal(deniedEvents.filter((item) => item.http_status === 403 && item.transport_method === "OPTIONS").length, 2);
  assert.ok(deniedEvents.every((item) => item.payload_inline === false));
});

test("public report access ignores attacker-supplied backdated time and uses the server clock", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const token = "expired-report-backdating-regression-token";
  await store.createShareableReport({
    source: "mock",
    shareToken: token,
    createdAt: "2026-07-12T06:00:00.000Z",
    expiresAt: "2026-07-12T08:00:00.000Z"
  });

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    now: "2026-07-12T09:00:00.000Z"
  }, async (url) => {
    const response = await fetch(`${url}/r/${token}?viewed_at=2026-07-12T07%3A00%3A00.000Z`);
    assert.equal(response.status, 410);
    assert.match(await response.text(), /expired/i);
  });

  const accessEvent = store.exportState().auditEvents.find((item) => item.access_result === "expired");
  assert.ok(accessEvent);
  assert.equal(accessEvent.viewed_at, "2026-07-12T09:00:00.000Z");
  assert.notEqual(accessEvent.viewed_at, "2026-07-12T07:00:00.000Z");
});

test("hosted live GitHub intent reaches an executor only after trusted route enforcement", async () => {
  let publishOptions = null;
  let decisionOptions = null;
  const store = {
    storage_mode: "external-test",
    github_executor_authority: "a1_trusted_worker",
    async recordAccessDecision() {
      return { persisted: true };
    },
    async publishGitHubCheckRun(options) {
      publishOptions = options;
      return {
        schema_version: "a3.github_check_publish_receipt.v1",
        status: "accepted_by_test_executor",
        dry_run: options.dryRun
      };
    }
  };

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" }),
    resolveTrustedReleaseAuthorization: async (options) => {
      decisionOptions = options;
      return trustedReleaseAuthorization(options);
    },
    resolveTrustedGitHubTarget: async () => trustedGitHubTarget("acme/refund-agent")
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/github/check-run/publish?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        repo: "acme/refund-agent",
        head_sha: "trusted-hosted-sha",
        allow_live: true,
        api_base_url: "https://attacker.invalid/github",
        token_env: "RELEASEFOUNDRY_API_KEY",
        decision_ledger_head_hash: "sha256:trusted-ledger-head",
        decision_record_id: "sha256:trusted-decision-record"
      })
    });
    assert.equal(response.status, 202);
    assert.equal((await response.json()).status, "accepted_by_test_executor");
  });

  assert.ok(publishOptions);
  assert.equal(publishOptions.dryRun, false);
  assert.equal(publishOptions.repo, "acme/refund-agent");
  assert.equal(publishOptions.headSha, "trusted-hosted-sha");
  assert.equal(publishOptions.decisionLedgerHeadHash, "sha256:trusted-ledger-head");
  assert.equal(publishOptions.decisionRecordId, "sha256:trusted-decision-record");
  assert.equal(publishOptions.apiBaseUrl, undefined);
  assert.equal(publishOptions.tokenEnvName, undefined);
  assert.equal(publishOptions.trustedReleaseAuthorization.authority, "a2_trusted_service");
  assert.equal(publishOptions.trustedGitHubTarget.authority, "a1_github_installation");
  assert.equal(decisionOptions.decisionLedgerHeadHash, "sha256:trusted-ledger-head");
  assert.equal(decisionOptions.decisionRecordId, "sha256:trusted-decision-record");
});

test("hosted live GitHub intent rejects non-A1 executors and client secret-routing fields", async () => {
  let publishCalled = false;
  const store = {
    storage_mode: "local-reference",
    async recordAccessDecision() {
      return { persisted: true };
    },
    async publishGitHubCheckRun() {
      publishCalled = true;
      return { status: "must-not-run" };
    }
  };

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" }),
    resolveTrustedReleaseAuthorization: async (options) => trustedReleaseAuthorization(options),
    resolveTrustedGitHubTarget: async () => trustedGitHubTarget("acme/refund-agent")
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/github/check-run/publish?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        repo: "acme/refund-agent",
        head_sha: "trusted-hosted-sha",
        allow_live: true,
        api_base_url: "https://attacker.invalid/github",
        token_env: "RELEASEFOUNDRY_API_KEY",
        decision_ledger_head_hash: "sha256:trusted-ledger-head",
        decision_record_id: "sha256:trusted-decision-record"
      })
    });
    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.equal(payload.error, "trusted_github_executor_required");
    assert.equal(payload.decision, "denied_requires_a1_trusted_github_worker");
    assert.doesNotMatch(JSON.stringify(payload), /attacker\.invalid|RELEASEFOUNDRY_API_KEY/);
  });

  assert.equal(publishCalled, false);
});

test("hosted live GitHub intent rejects a repository outside the tenant installation", async () => {
  let publishCalled = false;
  const store = {
    storage_mode: "external-test",
    github_executor_authority: "a1_trusted_worker",
    async recordAccessDecision() {
      return { persisted: true };
    },
    async publishGitHubCheckRun() {
      publishCalled = true;
      return { status: "must-not-run" };
    }
  };

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" }),
    resolveTrustedReleaseAuthorization: async (options) => trustedReleaseAuthorization(options),
    resolveTrustedGitHubTarget: async () => trustedGitHubTarget("acme/other-repository")
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/github/check-run/publish?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        repo: "attacker/target-repository",
        head_sha: "must-not-publish",
        allow_live: true,
        decision_ledger_head_hash: "sha256:trusted-ledger-head",
        decision_record_id: "sha256:trusted-decision-record"
      })
    });
    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.equal(payload.error, "trusted_github_target_required");
    assert.equal(payload.decision, "denied_untrusted_github_target");
    assert.doesNotMatch(JSON.stringify(payload), /attacker\/target-repository|acme\/other-repository/);
  });

  assert.equal(publishCalled, false);
});

test("hosted live GitHub intent never falls back to a store-local A2 allow claim", async () => {
  let publishCalled = false;
  const store = {
    storage_mode: "external-test",
    github_executor_authority: "a1_trusted_worker",
    async recordAccessDecision() {
      return { persisted: true };
    },
    async authorizeLiveRelease() {
      return { allowed: true, release_ready: true, upstream_decision: "allow" };
    },
    async publishGitHubCheckRun() {
      publishCalled = true;
      return { status: "must-not-run" };
    }
  };

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" })
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/github/check-run/publish?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        repo: "acme/refund-agent",
        head_sha: "must-not-publish",
        allow_live: true,
        decision_ledger_head_hash: "sha256:trusted-ledger-head",
        decision_record_id: "sha256:trusted-decision-record"
      })
    });
    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.equal(payload.error, "a2_release_decision_required");
    assert.equal(payload.decision, "denied_a2_trusted_authority_unavailable");
  });

  assert.equal(publishCalled, false);
});

test("hosted live GitHub intent is blocked while A2 Decision Ledger says release_ready=false", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal({ role: "owner" }),
    resolveTrustedReleaseAuthorization: async (options) => ({
      ...trustedReleaseAuthorization(options),
      allowed: false,
      release_ready: false,
      upstream_decision: "block",
      reason_code: "a2_release_not_ready"
    }),
    resolveTrustedGitHubTarget: async () => trustedGitHubTarget("acme/refund-agent")
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/github/check-run/publish?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        repo: "acme/refund-agent",
        head_sha: "must-not-publish",
        allow_live: true,
        decision_ledger_head_hash: "sha256:31c417d9232f3e2b0361f63b8aad305304774d28d0f68ed6e093f1a0bffa1e18",
        decision_record_id: "sha256:e19d38b6f189135256ed1afd9ad4f433cc0d5361a0a251adb936e469fa2e9687"
      })
    });
    assert.equal(response.status, 403);
    const payload = await response.json();
    assert.equal(payload.error, "a2_release_decision_required");
    assert.equal(payload.decision, "denied_by_a2_decision_ledger");
    assert.equal(payload.release_authorization.release_ready, false);
    assert.doesNotMatch(JSON.stringify(payload), /must-not-publish/);
  });

  assert.equal(store.exportState().githubPublishReceipts.length, 0);
});

function trustedReleaseAuthorization(options = {}) {
  return {
    schema_version: "a3.live_release_authorization.v1",
    authority: "a2_trusted_service",
    allowed: true,
    decision: "allowed_by_a2_decision_ledger",
    release_ready: true,
    upstream_decision: "allow",
    tenant_scope: SCOPE,
    decision_ledger: {
      head_hash: options.decisionLedgerHeadHash,
      record_id: options.decisionRecordId,
      chain_verified: true
    }
  };
}

function trustedGitHubTarget(repo) {
  return {
    authority: "a1_github_installation",
    repo,
    tenant_scope: SCOPE
  };
}

function trustedPrincipal(overrides = {}) {
  const role = overrides.role || "owner";
  return {
    trusted: true,
    authenticated: true,
    role,
    actor_hash: "actor_0123456789abcdef01234567",
    session: { state: "active" },
    permissions: [...A3_RBAC_ROLES[role]],
    expires_at: "2099-01-01T00:00:00.000Z",
    tenant_scope: SCOPE,
    ...overrides
  };
}

async function withServer(options, operation) {
  const { server, url } = await startA3ApiServer(options);
  try {
    return await operation(url);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}
