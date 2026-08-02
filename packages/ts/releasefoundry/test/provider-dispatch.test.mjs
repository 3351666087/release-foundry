import assert from "node:assert/strict";
import test from "node:test";

import {
  PROVIDER_DISPATCH_CAPABILITIES,
  PROVIDER_DISPATCH_CLIENT_VERSION,
  PROVIDER_DISPATCH_ERROR_CODES,
  PROVIDER_DISPATCH_RECONCILIATION_OUTCOMES,
  PROVIDER_DISPATCH_STATUSES,
  PROVIDER_DISPATCH_TERMINAL_STATES,
  ProviderDispatchClient,
  ProviderDispatchConflict,
  ProviderDispatchConflictError,
  ProviderDispatchError,
  ProviderDispatchFenceRejected,
  ProviderDispatchLeaseError,
  ProviderDispatchNotFound,
  ProviderDispatchProtocolError,
  ProviderDispatchValidationError,
  provider_dispatch_capability_manifest,
} from "../dist/provider-dispatch.js";

const scope = { tenantId: "tenant / cn", projectId: "project-a" };

function dispatch(overrides = {}) {
  return {
    schema_version: "releasefoundry.control_plane.v1",
    tenant_id: "tenant / cn",
    project_id: "project-a",
    dispatch_id: "dispatch-123",
    provider: "openai-compatible",
    operation: "responses.create",
    request_fingerprint: "a".repeat(64),
    status: "claimed",
    attempts: 1,
    fencing_token: 7,
    lease_owner_id: "worker-a",
    lease_expires_at: "2026-07-12T12:00:30.000Z",
    stream_observed: false,
    reconciliation_attempts: 0,
    created_at: "2026-07-12T12:00:00.000Z",
    updated_at: "2026-07-12T12:00:00.000Z",
    raw_payload_included: false,
    ...overrides,
  };
}

function response(body, status = 200, requestId = "request-1") {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-request-id": requestId },
  });
}

test("exports the exact Go provider dispatch status vocabulary", () => {
  assert.deepEqual(PROVIDER_DISPATCH_STATUSES, [
    "pending", "claimed", "indeterminate", "reconciling", "completed", "failed", "cancelled",
  ]);
});

test("exports the complete Python-compatible capability surface", () => {
  assert.equal(PROVIDER_DISPATCH_CLIENT_VERSION, "releasefoundry.provider_dispatch.v1");
  assert.deepEqual(PROVIDER_DISPATCH_TERMINAL_STATES, ["completed", "failed", "cancelled"]);
  assert.equal(
    PROVIDER_DISPATCH_RECONCILIATION_OUTCOMES,
    PROVIDER_DISPATCH_TERMINAL_STATES,
  );
  assert.equal(PROVIDER_DISPATCH_CAPABILITIES.authoritative_store, "postgresql");
  assert.equal(PROVIDER_DISPATCH_CAPABILITIES.terminal_stream_proof_binding, true);
  assert.equal(PROVIDER_DISPATCH_CAPABILITIES.raw_request_persisted, false);
  assert.deepEqual(provider_dispatch_capability_manifest(), {
    schema_version: "releasefoundry.provider_dispatch.v1",
    capabilities: { ...PROVIDER_DISPATCH_CAPABILITIES },
    states: [
      "cancelled", "claimed", "completed", "failed", "indeterminate", "pending", "reconciling",
    ],
    error_codes: [...PROVIDER_DISPATCH_ERROR_CODES].sort(),
    public_safe: true,
    routes: [
      "submit", "claim", "heartbeat", "observe-stream", "complete", "indeterminate",
      "reconciliation/claim", "get",
    ],
  });
});

test("Python-compatible error names preserve specific runtime classification", async () => {
  const conflict = new ProviderDispatchConflictError(
    "state_conflict",
    "conflict",
    409,
    "request-conflict",
    {},
  );
  const fence = new ProviderDispatchLeaseError(
    "stale_fence",
    "stale",
    409,
    "request-fence",
    {},
  );
  assert.equal(conflict instanceof ProviderDispatchConflict, true);
  assert.equal(fence instanceof ProviderDispatchFenceRejected, true);

  for (const [wireCode, ExpectedType] of [
    ["provider_dispatch_not_found", ProviderDispatchNotFound],
    ["provider_dispatch_validation", ProviderDispatchValidationError],
  ]) {
    const client = new ProviderDispatchClient({
      baseUrl: "https://runtime.example.test",
      fetch: async () => response({ error: { code: wireCode, message: "rejected" } },
        wireCode.endsWith("not_found") ? 404 : 422),
    });
    await assert.rejects(client.get(scope, "dispatch-123"), ExpectedType);
  }
});

test("submit and collection claim use the canonical plural routes and payloads", async () => {
  const calls = [];
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test/",
    apiKey: "secret-never-returned",
    fetch: async (url, init) => {
      calls.push({ url: String(url), init, body: init.body ? JSON.parse(init.body) : null });
      if (String(url).endsWith("/claim")) {
        return response({ result: {
          schema_version: "releasefoundry.control_plane.v1",
          status: "claimed",
          claimed: true,
          dispatch: dispatch(),
        } });
      }
      return response({ result: dispatch({ status: "pending", attempts: 0, fencing_token: 0 }) });
    },
  });

  const submitted = await client.submit(scope, {
    provider: "openai-compatible",
    operation: "responses.create",
    dispatchId: "dispatch-123",
    request: { modalities_present: ["text", "image", "audio", "file", "video"] },
  }, { requestId: "sdk-request" });
  const claimed = await client.claim(scope, {
    leaseOwnerId: "worker-a",
    leaseSeconds: 30,
    provider: "openai-compatible",
    operation: "responses.create",
  });

  assert.equal(submitted.status, "pending");
  assert.equal(claimed.dispatch.fencing_token, 7);
  assert.equal(
    calls[0].url,
    "https://runtime.example.test/v1/tenants/tenant%20%2F%20cn/projects/project-a/provider-dispatches",
  );
  assert.deepEqual(calls[0].body, {
    provider: "openai-compatible",
    operation: "responses.create",
    dispatch_id: "dispatch-123",
    request: { modalities_present: ["text", "image", "audio", "file", "video"] },
  });
  assert.equal(calls[0].init.headers.authorization, "Bearer secret-never-returned");
  assert.equal(calls[0].init.headers["x-request-id"], "sdk-request");
  assert.equal(calls[1].url.endsWith("/provider-dispatches/claim"), true);
  assert.deepEqual(calls[1].body, {
    lease_owner_id: "worker-a",
    lease_seconds: 30,
    provider: "openai-compatible",
    operation: "responses.create",
  });
});

test("claim represents empty queues without manufacturing a dispatch", async () => {
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async () => response({ result: {
      schema_version: "releasefoundry.control_plane.v1",
      status: "empty",
      claimed: false,
    } }),
  });
  assert.deepEqual(await client.claim(scope, { leaseOwnerId: "worker-a" }), {
    schema_version: "releasefoundry.control_plane.v1",
    status: "empty",
    claimed: false,
  });
});

test("heartbeat, observe-stream, complete, and indeterminate share fenced mutation shape", async () => {
  const calls = [];
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async (url, init) => {
      const operation = String(url).split("/").at(-1);
      calls.push({ operation, body: JSON.parse(init.body) });
      const status = operation === "complete" ? "completed"
        : operation === "indeterminate" ? "indeterminate"
        : "claimed";
      return response({ result: dispatch({ status }) });
    },
  });
  const lease = { leaseOwnerId: "worker-a", fencingToken: 7 };
  await client.heartbeat(scope, "dispatch-123", lease, 45);
  await client.observeStream(scope, "dispatch-123", lease, {
    schema_version: "releasefoundry.provider_stream.v1",
    stream_digest: "f".repeat(64),
    frame_count: 1,
  });
  await client.complete(
    scope,
    "dispatch-123",
    lease,
    { stream_digest: "f".repeat(64) },
    { finish_reason: "stop", usage: { total_tokens: 9 } },
    "provider-request-1",
  );
  await client.markIndeterminate(
    scope,
    "dispatch-123",
    lease,
    "provider outcome unknown",
    { code: "connection_reset" },
    "2026-07-12T12:01:00.000Z",
  );

  assert.deepEqual(calls.map(({ operation }) => operation), [
    "heartbeat", "observe-stream", "complete", "indeterminate",
  ]);
  for (const { body } of calls) {
    assert.equal(body.lease_owner_id, "worker-a");
    assert.equal(body.fencing_token, 7);
  }
  assert.deepEqual(calls[0].body, {
    lease_owner_id: "worker-a", fencing_token: 7, lease_seconds: 45,
  });
  assert.equal(calls[1].body.stream.frame_count, 1);
  assert.equal(calls[2].body.provider_request_id, "provider-request-1");
  assert.equal(calls[3].body.next_reconcile_at, "2026-07-12T12:01:00.000Z");
});

test("reconciliation claim uses the dedicated collection route and reconciling status", async () => {
  let captured;
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async (url, init) => {
      captured = { url: String(url), body: JSON.parse(init.body) };
      return response({ result: {
        schema_version: "releasefoundry.control_plane.v1",
        status: "reconciling",
        claimed: true,
        dispatch: dispatch({ status: "reconciling", reconciliation_attempts: 1 }),
      } });
    },
  });
  const claim = await client.claimReconciliation(scope, {
    leaseOwnerId: "reconciler-a",
    leaseSeconds: 60,
  });
  assert.equal(claim.dispatch.status, "reconciling");
  assert.equal(captured.url.endsWith("/provider-dispatches/reconciliation/claim"), true);
  assert.deepEqual(captured.body, { lease_owner_id: "reconciler-a", lease_seconds: 60 });
});

test("get validates the complete durable Go record shape", async () => {
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async (url) => {
      assert.equal(String(url).endsWith("/provider-dispatches/dispatch-123"), true);
      return response({ result: dispatch({ status: "completed", completed_at: "2026-07-12T12:02:00Z" }) });
    },
  });
  assert.equal((await client.get(scope, "dispatch-123")).status, "completed");
});

test("stable Go errors map without leaking transport implementation details", async () => {
  const cases = [
    ["provider_dispatch_conflict", ProviderDispatchConflictError, "idempotency_conflict", false],
    ["provider_dispatch_fence", ProviderDispatchLeaseError, "stale_fence", false],
    ["provider_dispatch_contention", ProviderDispatchError, "provider_dispatch_contention", true],
    ["provider_dispatch_unavailable", ProviderDispatchError, "provider_dispatch_unavailable", true],
    ["provider_dispatch_indeterminate", ProviderDispatchError, "provider_dispatch_indeterminate", true],
    ["provider_dispatch_deadline", ProviderDispatchError, "provider_dispatch_deadline", false],
  ];
  for (const [wireCode, ErrorType, expectedCode, retryable] of cases) {
    const client = new ProviderDispatchClient({
      baseUrl: "https://runtime.example.test",
      fetch: async () => response({
        error: { code: wireCode, message: "operation rejected", details: { dispatch_id: "dispatch-123" } },
      }, 409, `request-${wireCode}`),
    });
    await assert.rejects(
      client.get(scope, "dispatch-123"),
      (error) => error instanceof ErrorType
        && error.code === expectedCode
        && error.requestId === `request-${wireCode}`
        && error.retryable === retryable
        && !error.message.includes("postgres")
        && !error.message.includes("driver"),
    );
  }
});

test("transport cancellation and malformed successes remain stable and safe", async () => {
  const controller = new AbortController();
  controller.abort();
  const cancelled = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async () => { throw new Error("socket and database details"); },
  });
  await assert.rejects(
    cancelled.get(scope, "dispatch-123", { signal: controller.signal }),
    (error) => error.code === "provider_dispatch_cancelled"
      && !error.message.includes("socket")
      && !error.retryable,
  );

  const malformed = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async () => response({ result: { status: "completed" } }),
  });
  await assert.rejects(
    malformed.get(scope, "dispatch-123"),
    ProviderDispatchProtocolError,
  );
});

test("invalid public inputs fail before transport", () => {
  let calls = 0;
  const client = new ProviderDispatchClient({
    baseUrl: "https://runtime.example.test",
    fetch: async () => { calls += 1; return response({}); },
  });
  assert.throws(
    () => client.claim(scope, { leaseOwnerId: "worker", leaseSeconds: 0 }),
    (error) => error.code === "invalid_input",
  );
  assert.throws(
    () => client.complete(scope, "dispatch-123", { leaseOwnerId: "worker", fencingToken: 1 }, {}, {}),
    (error) => error.code === "invalid_input",
  );
  assert.throws(
    () => client.markIndeterminate(
      scope,
      "dispatch-123",
      { leaseOwnerId: "worker", fencingToken: 0 },
      "unknown",
      {},
    ),
    (error) => error.code === "invalid_input",
  );
  assert.equal(calls, 0);
});
