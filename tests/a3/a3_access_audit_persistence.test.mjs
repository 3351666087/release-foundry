import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { authorizeA3Operation } from "../../services/report/a3_auth_rbac_boundary.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";
import { createMemoryA3Store } from "../../services/report/a3_store.mjs";

const scope = {
  organization_id: "org-access-audit",
  tenant_id: "tenant-access-audit",
  workspace_id: "workspace-access-audit",
  project_id: "project-access-audit",
  environment_id: "staging"
};

test("A3 backend records metadata-only access decisions and meters API usage", async () => {
  const store = createMemoryA3Store({ storageMode: "memory" });
  const decision = authorizeA3Operation("read_dashboard", {
    role: "auditor",
    actor_hash: "actor_0123456789abcdef01234567",
    hosted_session: true,
    ...scope
  }, {
    requestId: "req-access-audit-001",
    traceId: "trace-access-audit-001"
  });

  const receipt = await store.recordAccessDecision(decision);
  assert.equal(receipt.schema_version, "a3.access_decision_audit_receipt.v1");
  assert.equal(receipt.persisted, true);
  assert.equal(receipt.storage_mode, "memory");
  assert.equal(receipt.safety.metadata_only, true);

  const state = store.exportState();
  const event = state.auditEvents.find((item) => item.event_id === receipt.audit_event_id);
  assert.ok(event);
  assert.equal(event.payload_inline, false);
  assert.equal(event.redaction_status, "metadata_only");
  assert.equal(event.tenant_id, scope.tenant_id);

  assert.equal(state.eventOutbox.length, 1);
  assert.equal(state.eventOutbox[0].usage_meter.meter, "api_requests");
  assert.equal(state.eventOutbox[0].payload_inline, false);

  const replay = await store.recordAccessDecision(decision);
  assert.equal(replay.idempotent_replay, true);
  assert.equal(store.exportState().auditEvents.length, 1);
});

test("A3 access decision persistence rejects unsafe or incomplete audit envelopes", async () => {
  const store = createMemoryA3Store();
  const decision = authorizeA3Operation("read_dashboard", {
    role: "auditor",
    hosted_session: true,
    ...scope
  });

  await assert.rejects(
    store.recordAccessDecision({
      ...decision,
      audit_event: {
        ...decision.audit_event,
        payload_inline: true,
        raw: `Authorization: Bearer ${"x".repeat(32)}`
      }
    }),
    /audit failed validation/i
  );
  assert.equal(store.exportState().auditEvents.length, 0);
});

test("SQLite persists access audit and outbox evidence across restart", async () => {
  const directory = await mkdtemp(join(tmpdir(), "a3-access-audit-"));
  const dbPath = join(directory, "a3.sqlite");
  try {
    const first = await createSqliteA3Store({ dbPath });
    const decision = authorizeA3Operation("read_dashboard", {
      role: "owner",
      actor_hash: "actor_fedcba9876543210fedcba98",
      hosted_session: true,
      ...scope
    }, {
      requestId: "req-access-audit-sqlite",
      traceId: "trace-access-audit-sqlite"
    });
    const receipt = await first.recordAccessDecision(decision);
    assert.equal(receipt.storage_mode, "sqlite");
    assert.equal(first.inspectSqliteState().operational_tables.audit_events, 1);
    first.close();

    const reopened = await createSqliteA3Store({ dbPath });
    const state = reopened.exportState();
    assert.equal(state.auditEvents.some((event) => event.event_id === receipt.audit_event_id), true);
    assert.equal(state.eventOutbox.some((event) => event.resource_id === receipt.audit_event_id), true);
    assert.equal(reopened.inspectSqliteState().operational_tables.audit_events, 1);
    reopened.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
