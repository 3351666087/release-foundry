import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  SESSION_LIFECYCLE_ERROR_CODES,
  SESSION_LIFECYCLE_ROUTES,
  SESSION_LIFECYCLE_SCHEMA_VERSION,
  SESSION_LIFECYCLE_STATUSES,
  SessionAccessToken,
  SessionAccessTokenDigest,
  SessionLifecycleError,
  SessionLifecycleHttpClient,
  SessionLifecycleMemoryStore,
  SessionRefreshToken,
  SessionRefreshTokenDigest,
  SessionRotationFamilyDigest,
  SessionTokenPair,
  SessionTokenPairReceipt,
  assertPublicSessionPayload,
  browserSessionRefreshRoute,
  parseRecentAuthDTO,
  parseSessionDTO,
  parseSessionRevocationDTO,
  sessionAuthenticateRoute,
  sessionCollectionRoute,
  sessionLifecycleContractManifest,
  sessionRecentAuthRoute,
  sessionRecoveryInvalidationRoute,
  sessionRefreshRoute,
  sessionRevokeAllRoute,
  sessionRevokeRoute,
  sessionRoute,
} from "../dist/session-lifecycle.js";

const NOW = Date.parse("2026-07-11T04:00:00.000Z");
const scope = { tenantId: "tenant_main", projectId: "project_main", accountId: "account_main" };

function digest(label) {
  return createHash("sha256").update(label, "utf8").digest("hex");
}

function at(minutes = 0, milliseconds = 0) {
  return new Date(NOW + minutes * 60_000 + milliseconds).toISOString();
}

function store() {
  return new SessionLifecycleMemoryStore({ clock: () => new Date(NOW) });
}

function issueOptions(label = "primary", overrides = {}) {
  return {
    ...scope,
    accessTokenDigest: digest(`access:${label}:0`),
    refreshTokenDigest: digest(`refresh:${label}:0`),
    rotationFamilyDigest: digest(`family:${label}`),
    accessExpiresAt: at(10),
    refreshExpiresAt: at(480),
    authenticatedAt: at(0),
    assuranceLevel: "aal1",
    sessionId: `session_${label}`,
    rotationFamilyId: `family_${label}`,
    idempotencyKey: `issue_${label}`,
    now: at(0),
    ...overrides,
  };
}

function refreshOptions(label = "primary", generation = 0, nextGeneration = 1, overrides = {}) {
  return {
    ...scope,
    currentRefreshTokenDigest: digest(`refresh:${label}:${generation}`),
    newAccessTokenDigest: digest(`access:${label}:${nextGeneration}`),
    newRefreshTokenDigest: digest(`refresh:${label}:${nextGeneration}`),
    accessExpiresAt: at(11),
    idempotencyKey: `refresh_${label}_${generation}`,
    now: at(1),
    ...overrides,
  };
}

function publicSession(overrides = {}) {
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: "tenant_main",
    project_id: "project_main",
    account_id: "account_main",
    session_id: "session_primary",
    rotation_family_id: "family_primary",
    generation: 0,
    status: "active",
    assurance_level: "aal1",
    authenticated_at: "2026-07-11T04:00:00.000000Z",
    created_at: "2026-07-11T04:00:00.000000Z",
    access_expires_at: "2026-07-11T04:10:00.000000Z",
    refresh_expires_at: "2026-07-11T12:00:00.000000Z",
    last_rotated_at: null,
    revoked_at: null,
    revoke_reason_code: null,
    access_token_present: true,
    refresh_token_present: true,
    ...overrides,
  };
}

function revocation(overrides = {}) {
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: "tenant_main",
    project_id: "project_main",
    account_id: "account_main",
    reason_code: "user_revoked",
    revoked_at: "2026-07-11T04:01:00.000000Z",
    revoked_session_ids: ["session_primary"],
    revoked_count: 1,
    ...overrides,
  };
}

function recentAuth() {
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: "tenant_main",
    project_id: "project_main",
    account_id: "account_main",
    session_id: "session_primary",
    assurance_level: "aal1",
    authenticated_at: "2026-07-11T04:00:00.000000Z",
    valid_until: "2026-07-11T04:05:00.000000Z",
    recent: true,
  };
}

function response(payload, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": contentType } });
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function fingerprint(value) {
  return createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("hex");
}

function assertPublicDigestFree(value) {
  const text = JSON.stringify(value);
  assert.doesNotMatch(text, /"(?:access_token_digest|refresh_token_digest|rotation_family_digest)"/u);
  assert.equal(text.includes(digest("access:primary:0")), false);
  assert.equal(text.includes(digest("refresh:primary:0")), false);
}

test("contract manifest exactly exposes the stable Python snake_case shape", () => {
  const manifest = sessionLifecycleContractManifest();
  assert.deepEqual(manifest, {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    digest_only: true,
    rotation: true,
    reuse_detection: true,
    revocation: true,
    recent_auth: true,
    recovery: true,
    statuses: [...SESSION_LIFECYCLE_STATUSES],
    stable_error_codes: [...SESSION_LIFECYCLE_ERROR_CODES],
    routes: SESSION_LIFECYCLE_ROUTES.map((route) => ({ ...route })),
    invariants: {
      tenant_project_account_isolation: true,
      one_active_generation_per_rotation_family: true,
      refresh_rotation_is_atomic: true,
      reused_refresh_revokes_active_family: true,
      revoke_one_is_scoped: true,
      revoke_all_is_scoped: true,
      recent_auth_uses_original_authentication_time: true,
      recovery_invalidates_active_sessions: true,
      snapshots_are_digest_only: true,
      public_dto_excludes_token_digests: true,
      access_refresh_token_classes_are_distinct: true,
      session_token_receipts_are_one_time: true,
      refresh_bearer_never_authenticates_as_access: true,
      public_serialization_redacts_bearers: true,
    },
  });
  assert.doesNotThrow(() => assertPublicSessionPayload(manifest));
});

test("typed tokens derive non-interchangeable digests for the store", () => {
  const lifecycle = store();
  const pair = new SessionTokenPair(
    new SessionAccessToken("access.primary.opaque-bearer"),
    new SessionRefreshToken("refresh.primary.opaque-bearer"),
  );
  const issued = lifecycle.issueSession(issueOptions("typed", {
    accessTokenDigest: pair.accessDigest(),
    refreshTokenDigest: pair.refreshDigest(),
    rotationFamilyDigest: SessionRotationFamilyDigest.fromMaterial("rotation.primary.opaque-material"),
  }));
  assert.deepEqual(lifecycle.authenticateAccess({
    ...scope,
    accessTokenDigest: pair.accessDigest(),
    now: at(0),
  }), issued);
  assert.throws(
    () => lifecycle.authenticateAccess({ ...scope, accessTokenDigest: pair.refreshDigest(), now: at(0) }),
    (error) => error.code === "session_invalid_request",
  );
  assert.throws(
    () => lifecycle.refreshSession({
      ...scope,
      currentRefreshTokenDigest: pair.accessDigest(),
      newAccessTokenDigest: new SessionAccessTokenDigest(digest("next-access")),
      newRefreshTokenDigest: new SessionRefreshTokenDigest(digest("next-refresh")),
      accessExpiresAt: at(11),
      idempotencyKey: "wrong_refresh_class",
      now: at(1),
    }),
    (error) => error.code === "session_invalid_request",
  );
  assert.equal(lifecycle.getSession({ ...scope, sessionId: "session_typed", now: at(0) }).status, "active");
});

test("token pair receipt is one use and public serialization is redacted", () => {
  const accessValue = "access.receipt.private-bearer";
  const refreshValue = "refresh.receipt.private-bearer";
  const pair = new SessionTokenPair(new SessionAccessToken(accessValue), new SessionRefreshToken(refreshValue));
  const receipt = new SessionTokenPairReceipt({
    sessionId: "session_receipt",
    keyVersion: "session_hmac_v3",
    accessExpiresAt: at(10),
    refreshExpiresAt: at(480),
    tokenPair: pair,
    now: at(0),
  });
  const publicJson = JSON.stringify(receipt);
  const safeText = `${String(receipt)} ${String(pair)} ${publicJson}`;
  assert.equal(safeText.includes(accessValue), false);
  assert.equal(safeText.includes(refreshValue), false);
  assert.equal(safeText.includes(pair.accessDigest().forStorage()), false);
  assert.equal(safeText.includes(pair.refreshDigest().forStorage()), false);
  assert.deepEqual(JSON.parse(publicJson), {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    session_id: "session_receipt",
    key_version: "session_hmac_v3",
    access_expires_at: "2026-07-11T04:10:00.000000Z",
    refresh_expires_at: "2026-07-11T12:00:00.000000Z",
    access_token_present: true,
    refresh_token_present: true,
  });

  const transferred = receipt.takeTokenPair();
  assert.equal(receipt.toJSON().access_token_present, false);
  assert.equal(receipt.toJSON().refresh_token_present, false);
  assert.throws(() => receipt.takeTokenPair(), (error) => error.code === "session_invalid_request");
  assert.equal(transferred.takeAccessToken(), accessValue);
  assert.throws(() => transferred.takeAccessToken(), (error) => error.code === "session_invalid_request");
  assert.deepEqual(transferred.toJSON(), { access_token_present: false, refresh_token_present: true });
  assert.equal(transferred.takeRefreshToken(), refreshValue);
  assert.deepEqual(transferred.toJSON(), { access_token_present: false, refresh_token_present: false });
});

test("token objects and digests never serialize raw material", () => {
  const accessValue = "access.serialization.private-bearer";
  const refreshValue = "refresh.serialization.private-bearer";
  const access = new SessionAccessToken(accessValue);
  const refresh = new SessionRefreshToken(refreshValue);
  const accessDigest = access.digest();
  const refreshDigest = refresh.digest();
  const safe = JSON.stringify({ access, refresh, accessDigest, refreshDigest });
  const rendered = `${String(access)} ${String(refresh)} ${String(accessDigest)} ${String(refreshDigest)} ${safe}`;
  assert.equal(rendered.includes(accessValue), false);
  assert.equal(rendered.includes(refreshValue), false);
  assert.equal(rendered.includes(accessDigest.forStorage()), false);
  assert.equal(rendered.includes(refreshDigest.forStorage()), false);
  assert.doesNotThrow(() => assertPublicSessionPayload(JSON.parse(safe)));
});

test("token receipt rejects invalid or expired lifetimes without consuming", () => {
  const pair = new SessionTokenPair(
    new SessionAccessToken("access.expiry.private-bearer"),
    new SessionRefreshToken("refresh.expiry.private-bearer"),
  );
  assert.throws(() => new SessionTokenPairReceipt({
    sessionId: "session_expiry",
    keyVersion: "session_hmac_v3",
    accessExpiresAt: at(10),
    refreshExpiresAt: at(10),
    tokenPair: pair,
    now: at(0),
  }), (error) => error.code === "session_invalid_request");
  assert.throws(() => new SessionTokenPairReceipt({
    sessionId: "session_expiry",
    keyVersion: "session_hmac_v3",
    accessExpiresAt: at(0),
    refreshExpiresAt: at(60),
    tokenPair: pair,
    now: at(0),
  }), (error) => error.code === "session_invalid_request");
  assert.deepEqual(pair.toJSON(), { access_token_present: true, refresh_token_present: true });
  pair.discard();
});

test("route builders include getSession/sessionRoute parity and encode every segment", () => {
  assert.equal(
    sessionCollectionRoute("project one", "account/one"),
    "/v1/projects/project%20one/accounts/account%2Fone/sessions",
  );
  assert.equal(
    sessionRoute("project one", "account/one", "session?one"),
    "/v1/projects/project%20one/accounts/account%2Fone/sessions/session%3Fone",
  );
  assert.equal(sessionAuthenticateRoute("p", "a"), "/v1/projects/p/accounts/a/sessions/authenticate");
  assert.equal(sessionRefreshRoute("p", "a"), "/v1/projects/p/accounts/a/sessions/refresh");
  assert.equal(browserSessionRefreshRoute("p", "a"), "/v1/projects/p/accounts/a/browser-sessions/refresh");
  assert.equal(sessionRevokeRoute("p", "a", "s"), "/v1/projects/p/accounts/a/sessions/s/revoke");
  assert.equal(sessionRevokeAllRoute("p", "a"), "/v1/projects/p/accounts/a/sessions/revoke-all");
  assert.equal(sessionRecentAuthRoute("p", "a", "s"), "/v1/projects/p/accounts/a/sessions/s/recent-auth");
  assert.equal(sessionRecoveryInvalidationRoute("p", "a"), "/v1/projects/p/accounts/a/sessions/recovery-invalidate");
});

test("issue stores digests but returns the exact strict public DTO", () => {
  const lifecycle = store();
  const issued = lifecycle.issueSession(issueOptions());
  assert.deepEqual(issued, publicSession());
  assertPublicDigestFree(issued);
  const snapshot = lifecycle.snapshotState();
  assert.equal(snapshot.storage_mode, "digest_only");
  assert.equal(snapshot.families[0].generations[0].access_token_digest, digest("access:primary:0"));
});

test("invalid digest is rejected without echoing caller material or mutating state", () => {
  const lifecycle = store();
  const callerValue = "not_a_sha256_digest";
  assert.throws(
    () => lifecycle.issueSession(issueOptions("bad", { accessTokenDigest: callerValue })),
    (error) => error.code === "session_invalid_request" && !error.message.includes(callerValue),
  );
  assert.deepEqual(lifecycle.listSessions(scope), []);
});

test("issue idempotency replay returns the original session", () => {
  const lifecycle = store();
  const first = lifecycle.issueSession(issueOptions("same", { idempotencyKey: "same_issue" }));
  const second = lifecycle.issueSession(issueOptions("same", { idempotencyKey: "same_issue" }));
  assert.deepEqual(second, first);
  assert.equal(lifecycle.listSessions(scope).length, 1);
});

test("issue idempotency conflict uses a stable code and creates no second family", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("first", { idempotencyKey: "shared_issue" }));
  assert.throws(
    () => lifecycle.issueSession(issueOptions("second", { idempotencyKey: "shared_issue" })),
    (error) => error.code === "session_digest_conflict",
  );
  assert.deepEqual(lifecycle.listSessions(scope).map((item) => item.session_id), ["session_first"]);
});

test("token and family digest collisions are global across scopes", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("first"));
  assert.throws(
    () => lifecycle.issueSession(issueOptions("other", {
      tenantId: "tenant_other",
      projectId: "project_other",
      accountId: "account_other",
      accessTokenDigest: digest("access:first:0"),
    })),
    (error) => error.code === "session_digest_conflict",
  );
  assert.deepEqual(lifecycle.listSessions({ tenantId: "tenant_other", projectId: "project_other", accountId: "account_other" }), []);
});

test("refresh keeps one stable session/family and advances an internal generation", () => {
  const lifecycle = store();
  const issued = lifecycle.issueSession(issueOptions("primary", { authenticatedAt: at(-2) }));
  const rotated = lifecycle.refreshSession(refreshOptions());
  assert.equal(rotated.session_id, issued.session_id);
  assert.equal(rotated.rotation_family_id, issued.rotation_family_id);
  assert.equal(rotated.generation, 1);
  assert.equal(rotated.authenticated_at, issued.authenticated_at);
  assert.equal(rotated.last_rotated_at, "2026-07-11T04:01:00.000000Z");
  assert.deepEqual(lifecycle.snapshot().families[0].generations.map((item) => item.status), ["rotated", "active"]);
});

test("same refresh idempotency replay does not trigger reuse detection", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  const first = lifecycle.refreshSession(refreshOptions("primary", 0, 1, { idempotencyKey: "same_refresh" }));
  const replay = lifecycle.refreshSession(refreshOptions("primary", 0, 1, { idempotencyKey: "same_refresh" }));
  assert.deepEqual(replay, first);
  assert.equal(lifecycle.snapshot().families[0].generations.length, 2);
});

test("old refresh reuse revokes every generation and preserves reuse tombstones", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  lifecycle.refreshSession(refreshOptions());
  assert.throws(
    () => lifecycle.refreshSession(refreshOptions("primary", 0, 2, {
      idempotencyKey: "attacker_reuse",
      now: at(2),
      accessExpiresAt: at(12),
    })),
    (error) => error.code === "session_refresh_reused",
  );
  const current = lifecycle.getSession({ ...scope, sessionId: "session_primary", now: at(2) });
  assert.equal(current.status, "revoked");
  assert.equal(current.revoke_reason_code, "refresh_reuse_detected");
  const family = lifecycle.snapshot().families[0];
  assert.equal(family.reuse_detected_at, "2026-07-11T04:02:00.000000Z");
  assert.ok(family.generations.every((item) => item.status === "revoked" && item.revoke_reason_code === "refresh_reuse_detected"));
  assert.throws(
    () => lifecycle.authenticateAccess({ ...scope, accessTokenDigest: digest("access:primary:1"), now: at(2) }),
    (error) => error.code === "session_refresh_reused",
  );
});

test("cross-scope refresh probe cannot revoke the matching family", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  lifecycle.refreshSession(refreshOptions());
  assert.throws(
    () => lifecycle.refreshSession(refreshOptions("primary", 0, 2, {
      tenantId: "tenant_other",
      projectId: "project_other",
      accountId: "account_other",
      idempotencyKey: "cross_scope",
      now: at(2),
      accessExpiresAt: at(12),
    })),
    (error) => error.code === "session_scope_mismatch",
  );
  assert.equal(lifecycle.getSession({ ...scope, sessionId: "session_primary" }).status, "active");
});

test("access expiry boundary blocks access while refresh remains usable", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("primary", { accessExpiresAt: at(5) }));
  assert.throws(
    () => lifecycle.authenticateAccess({ ...scope, accessTokenDigest: digest("access:primary:0"), now: at(5) }),
    (error) => error.code === "session_expired",
  );
  assert.equal(lifecycle.refreshSession(refreshOptions("primary", 0, 1, { now: at(5), accessExpiresAt: at(15) })).generation, 1);
});

test("refresh expiry boundary is closed and marks the family expired", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("primary", { accessExpiresAt: at(5), refreshExpiresAt: at(20) }));
  assert.throws(
    () => lifecycle.refreshSession(refreshOptions("primary", 0, 1, { now: at(20), accessExpiresAt: at(25) })),
    (error) => error.code === "session_expired",
  );
  assert.equal(lifecycle.getSession({ ...scope, sessionId: "session_primary", now: at(20) }).status, "expired");
});

test("refresh cannot extend the absolute family lifetime and failure is atomic", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  assert.throws(
    () => lifecycle.refreshSession(refreshOptions("primary", 0, 1, { refreshExpiresAt: at(481) })),
    /cannot extend/u,
  );
  assert.equal(lifecycle.getSession({ ...scope, sessionId: "session_primary" }).generation, 0);
});

test("revoke-one revokes one family and is key/state idempotent", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("first"));
  lifecycle.issueSession(issueOptions("second"));
  const first = lifecycle.revokeSession({ ...scope, sessionId: "session_first", idempotencyKey: "revoke_first", now: at(1) });
  const replay = lifecycle.revokeSession({ ...scope, sessionId: "session_first", idempotencyKey: "revoke_first", now: at(2) });
  const repeated = lifecycle.revokeSession({ ...scope, sessionId: "session_first", idempotencyKey: "revoke_again", now: at(2) });
  assert.deepEqual(replay, first);
  assert.equal(first.revoked_count, 1);
  assert.equal(repeated.revoked_count, 0);
  assert.equal(lifecycle.getSession({ ...scope, sessionId: "session_second" }).status, "active");
});

test("revoke-all is isolated by tenant, project, and account", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("one"));
  lifecycle.issueSession(issueOptions("two"));
  lifecycle.issueSession(issueOptions("other", { accountId: "account_other" }));
  const result = lifecycle.revokeAllSessions({ ...scope, idempotencyKey: "revoke_all", now: at(1) });
  assert.deepEqual(result.revoked_session_ids, ["session_one", "session_two"]);
  assert.equal(result.reason_code, "revoke_all");
  assert.equal(lifecycle.getSession({ ...scope, accountId: "account_other", sessionId: "session_other" }).status, "active");
});

test("recent-auth accepts the exact boundary and rejects stale or insufficient assurance", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  const recent = lifecycle.assertRecentAuth({ ...scope, sessionId: "session_primary", maxAgeSeconds: 300, now: at(5) });
  assert.deepEqual(recent, recentAuth());
  assert.throws(
    () => lifecycle.assertRecentAuth({ ...scope, sessionId: "session_primary", maxAgeSeconds: 300, now: at(5, 1) }),
    (error) => error.code === "session_recent_auth_required",
  );
  assert.throws(
    () => lifecycle.assertRecentAuth({ ...scope, sessionId: "session_primary", maxAgeSeconds: 300, minimumAssuranceLevel: "aal2", now: at(1) }),
    (error) => error.code === "session_recent_auth_required",
  );
});

test("recent-auth preserves Python-compatible microsecond boundary precision", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  assert.equal(
    lifecycle.assertRecentAuth({
      ...scope,
      sessionId: "session_primary",
      maxAgeSeconds: 300,
      now: "2026-07-11T04:05:00.000000Z",
    }).recent,
    true,
  );
  assert.throws(
    () => lifecycle.assertRecentAuth({
      ...scope,
      sessionId: "session_primary",
      maxAgeSeconds: 300,
      now: "2026-07-11T04:05:00.000001Z",
    }),
    (error) => error.code === "session_recent_auth_required",
  );
});

test("refresh preserves original authentication time and cannot make auth recent", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("primary", { authenticatedAt: at(-30) }));
  const refreshed = lifecycle.refreshSession(refreshOptions());
  assert.equal(refreshed.authenticated_at, "2026-07-11T03:30:00.000000Z");
  assert.throws(
    () => lifecycle.assertRecentAuth({ ...scope, sessionId: "session_primary", maxAgeSeconds: 300, now: at(1) }),
    (error) => error.code === "session_recent_auth_required",
  );
});

test("recovery invalidation is scoped, replayable, and conflict checked", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("target"));
  lifecycle.issueSession(issueOptions("other", { accountId: "account_other" }));
  const options = { ...scope, recoveryId: "recovery_one", idempotencyKey: "recover", now: at(1) };
  const first = lifecycle.invalidateForRecovery(options);
  const replay = lifecycle.invalidateForRecovery({ ...options, now: at(2) });
  assert.deepEqual(replay, first);
  assert.deepEqual(first.revoked_session_ids, ["session_target"]);
  assert.equal(first.reason_code, "account_recovery");
  assert.throws(
    () => lifecycle.invalidateForRecovery({ ...options, recoveryId: "recovery_two", now: at(2) }),
    (error) => error.code === "session_digest_conflict",
  );
  assert.equal(lifecycle.getSession({ ...scope, accountId: "account_other", sessionId: "session_other" }).status, "active");
});

test("snapshot/restore preserves generations, tombstones, integrity, and idempotency", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions("primary", { idempotencyKey: "issue_restore" }));
  const rotated = lifecycle.refreshSession(refreshOptions("primary", 0, 1, { idempotencyKey: "refresh_restore" }));
  const snapshot = lifecycle.snapshotState();
  const payload = Object.fromEntries(Object.entries(snapshot).filter(([key]) => key !== "integrity"));
  assert.equal(snapshot.integrity.payload_sha256, fingerprint(payload));
  const restored = SessionLifecycleMemoryStore.fromSnapshot(structuredClone(snapshot), { clock: () => new Date(NOW) });
  assert.deepEqual(restored.getSession({ ...scope, sessionId: "session_primary" }), rotated);
  assert.equal(restored.issueSession(issueOptions("primary", { idempotencyKey: "issue_restore" })).session_id, rotated.session_id);
  assert.deepEqual(restored.refreshSession(refreshOptions("primary", 0, 1, { idempotencyKey: "refresh_restore" })), rotated);
  assert.throws(
    () => restored.refreshSession(refreshOptions("primary", 0, 2, { idempotencyKey: "reuse_restore", now: at(2), accessExpiresAt: at(12) })),
    (error) => error.code === "session_refresh_reused",
  );
});

test("restore rejects integrity tampering atomically", () => {
  const lifecycle = store();
  const original = lifecycle.issueSession(issueOptions());
  const tampered = structuredClone(lifecycle.snapshot());
  tampered.families[0].generations[0].generation = 7;
  assert.throws(() => lifecycle.restoreState(tampered), (error) => error.code === "session_invalid_request");
  assert.deepEqual(lifecycle.getSession({ ...scope, sessionId: "session_primary" }), original);
});

test("restore rejects structurally invalid snapshots even with a recomputed hash", () => {
  const lifecycle = store();
  lifecycle.issueSession(issueOptions());
  const tampered = structuredClone(lifecycle.snapshot());
  tampered.families[0].generations[0].status = "rotated";
  const payload = Object.fromEntries(Object.entries(tampered).filter(([key]) => key !== "integrity"));
  tampered.integrity.payload_sha256 = fingerprint(payload);
  assert.throws(
    () => SessionLifecycleMemoryStore.fromSnapshot(tampered),
    (error) => error.code === "session_invalid_request",
  );
});

test("public guard recursively rejects secret/digest aliases and credential-shaped values", () => {
  for (const key of [
    "access_token", "accessTokenDigest", "refresh-token", "refreshTokenDigest",
    "rotationFamilyDigest", "Authorization", "clientSecret", "session_token",
  ]) {
    assert.throws(
      () => assertPublicSessionPayload({ safe: [{ nested: { [key]: "synthetic_value" } }] }),
      (error) => error.code === "session_invalid_request",
    );
  }
  const bearer = `Bearer ${"a".repeat(16)}.${"b".repeat(16)}.${"c".repeat(12)}`;
  assert.throws(
    () => assertPublicSessionPayload({ message: bearer }),
    (error) => error.code === "session_invalid_request" && !error.message.includes(bearer),
  );
});

test("strict DTO parsers reject unknown fields and inconsistent state", () => {
  assert.deepEqual(parseSessionDTO(publicSession()), publicSession());
  assert.deepEqual(parseSessionRevocationDTO(revocation()), revocation());
  assert.deepEqual(parseRecentAuthDTO(recentAuth()), recentAuth());
  assert.throws(() => parseSessionDTO({ ...publicSession(), metadata: {} }), /fields/u);
  assert.throws(() => parseSessionDTO({
    ...publicSession(),
    status: "revoked",
    access_token_present: false,
    refresh_token_present: false,
  }), /revocation metadata/u);
  assert.throws(() => parseSessionRevocationDTO({ ...revocation(), revoked_count: 2 }), /count/u);
});

test("typed HTTP digest methods use canonical routes and private request channels", async () => {
  const calls = [];
  const client = new SessionLifecycleHttpClient({
    baseUrl: "https://api.example.invalid/",
    fetch: async (url, init) => {
      calls.push({ url: String(url), init });
      return response({ result: publicSession({ generation: calls.length - 1 }) });
    },
  });
  await client.issueSession({
    ...scope,
    accessTokenDigest: digest("access:primary:0"),
    refreshTokenDigest: digest("refresh:primary:0"),
    rotationFamilyDigest: digest("family:primary"),
    accessExpiresAt: at(10),
    refreshExpiresAt: at(480),
  });
  await client.authenticateAccessToken({ ...scope, accessTokenDigest: digest("access:primary:0") });
  await client.rotateRefreshToken({
    ...scope,
    refreshTokenDigest: digest("refresh:primary:0"),
    nextAccessTokenDigest: digest("access:primary:1"),
    nextRefreshTokenDigest: digest("refresh:primary:1"),
    accessExpiresAt: at(11),
    refreshExpiresAt: at(480),
  });
  assert.deepEqual(calls.map((call) => new URL(call.url).pathname), [
    "/v1/projects/project_main/accounts/account_main/sessions",
    "/v1/projects/project_main/accounts/account_main/sessions/authenticate",
    "/v1/projects/project_main/accounts/account_main/sessions/refresh",
  ]);
  assert.equal(JSON.parse(calls[0].init.body).assurance_level, "aal1");
  assert.equal(JSON.parse(calls[2].init.body).next_refresh_token_digest, digest("refresh:primary:1"));
});

test("typed HTTP getSession uses sessionRoute and tenant isolation query", async () => {
  let captured;
  const client = new SessionLifecycleHttpClient({
    baseUrl: "https://api.example.invalid",
    fetch: async (url, init) => {
      captured = { url: String(url), init };
      return response({ result: publicSession() });
    },
  });
  const result = await client.getSession({ ...scope, sessionId: "session/primary" });
  const url = new URL(captured.url);
  assert.equal(url.pathname, "/v1/projects/project_main/accounts/account_main/sessions/session%2Fprimary");
  assert.equal(url.searchParams.get("tenant_id"), "tenant_main");
  assert.equal(captured.init.method, "GET");
  assert.equal(result.session_id, "session_primary");
});

test("typed HTTP public methods cover list/create/refresh/revoke/recent-auth/recovery", async () => {
  const calls = [];
  const client = new SessionLifecycleHttpClient({
    baseUrl: "https://api.example.invalid",
    fetch: async (url, init) => {
      const path = new URL(String(url)).pathname;
      calls.push({ path, init });
      if (init.method === "GET") return response({ result: { sessions: [publicSession()] } });
      if (path.endsWith("/recent-auth")) return response({ result: recentAuth() });
      if (path.endsWith("/revoke") || path.endsWith("/revoke-all") || path.endsWith("/recovery-invalidate")) {
        return response({ result: revocation({
          reason_code: path.endsWith("/revoke-all") ? "revoke_all" : path.endsWith("/recovery-invalidate") ? "account_recovery" : "user_revoked",
        }) });
      }
      return response({ result: publicSession({ generation: path.endsWith("/refresh") ? 1 : 0 }) });
    },
  });
  assert.equal((await client.listSessions(scope)).length, 1);
  await client.createSession({ ...scope, credentialId: "credential_1", idempotencyKey: "create_1" });
  await client.refreshSession({ ...scope, sessionId: "session_primary", idempotencyKey: "refresh_1" });
  await client.revokeSession({ ...scope, sessionId: "session_primary", idempotencyKey: "revoke_1" });
  await client.revokeAllSessions({ ...scope, idempotencyKey: "revoke_all_1" });
  await client.assertRecentAuth({ ...scope, sessionId: "session_primary", maxAgeSeconds: 300 });
  await client.invalidateForRecovery({ ...scope, recoveryId: "recovery_1", idempotencyKey: "recovery_idem" });
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    tenant_id: "tenant_main",
    credential_id: "credential_1",
    assurance_level: "aal1",
    idempotency_key: "create_1",
  });
  assert.deepEqual(JSON.parse(calls[2].init.body), {
    tenant_id: "tenant_main",
    session_id: "session_primary",
    idempotency_key: "refresh_1",
  });
  assert.equal(calls.at(-1).path.endsWith("/recovery-invalidate"), true);
});

test("HTTP success responses fail closed on secrets and unknown DTO fields", async () => {
  for (const payload of [
    { result: { ...publicSession(), refreshTokenDigest: digest("leak") } },
    { result: { ...publicSession(), unknown_server_field: true } },
  ]) {
    const client = new SessionLifecycleHttpClient({
      baseUrl: "http://127.0.0.1:8787",
      fetch: async () => response(payload),
    });
    await assert.rejects(
      client.getSession({ ...scope, sessionId: "session_primary" }),
      (error) => error.code === "session_invalid_request" && !error.message.includes(digest("leak")),
    );
  }
});

test("HTTP errors retain stable codes but discard private server detail", async () => {
  const privateValue = `Bearer ${"x".repeat(40)}`;
  const client = new SessionLifecycleHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async () => response({ error: { code: "session_refresh_reused", message: privateValue } }, 409),
  });
  await assert.rejects(
    client.refreshSession({ ...scope, sessionId: "session_primary", idempotencyKey: "refresh" }),
    (error) => error.code === "session_refresh_reused" && !JSON.stringify(error.toJSON()).includes(privateValue),
  );
});

test("HTTP client validates URL, JSON, timeout, and caller abort", async () => {
  assert.throws(() => new SessionLifecycleHttpClient({ baseUrl: "ftp://example.com" }), SessionLifecycleError);
  assert.throws(() => new SessionLifecycleHttpClient({ baseUrl: "http://user:pass@example.com" }), SessionLifecycleError);
  const nonJson = new SessionLifecycleHttpClient({
    baseUrl: "http://localhost",
    fetch: async () => response("bad", 200, "text/plain"),
  });
  await assert.rejects(nonJson.listSessions(scope), (error) => error.code === "session_store_failed");

  const timeout = new SessionLifecycleHttpClient({
    baseUrl: "http://localhost",
    timeoutMs: 5,
    fetch: async (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("private")), { once: true });
    }),
  });
  await assert.rejects(timeout.listSessions(scope), (error) => error.status === 504 && error.retryable);

  const controller = new AbortController();
  controller.abort();
  const aborted = new SessionLifecycleHttpClient({
    baseUrl: "http://localhost",
    signal: controller.signal,
    fetch: async () => { throw new Error("private"); },
  });
  await assert.rejects(aborted.listSessions(scope), (error) => error.status === 499);
});
