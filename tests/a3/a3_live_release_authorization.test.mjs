import assert from "node:assert/strict";
import { test } from "node:test";

import {
  A3StoreValidationError,
  createMemoryA3Store
} from "../../services/report/a3_store.mjs";
import { a2CanonicalHash } from "../../services/report/a3_trusted_release_authority.mjs";

const SCOPE = Object.freeze({
  organization_id: "org-release",
  tenant_id: "tenant-release",
  workspace_id: "workspace-release",
  project_id: "project-release",
  environment_id: "production"
});
const GENESIS_HASH = `sha256:${"0".repeat(64)}`;

test("A3 live release authorization verifies and consumes an A2 allow Decision Ledger", async () => {
  const spine = trustedSpine({ releaseReady: true, decision: "allow" });
  const store = storeWithDecision(spine);
  const authorization = await store.authorizeLiveRelease({
    source: "release-source",
    ...scopeOptions(SCOPE),
    enforceScope: true,
    decisionLedgerHeadHash: spine.decision_ledger.head_hash,
    decisionRecordId: spine.decision_ledger.records[0].record_id
  });

  assert.equal(authorization.allowed, true);
  assert.equal(authorization.decision, "allowed_by_a2_decision_ledger");
  assert.equal(authorization.release_ready, true);
  assert.equal(authorization.upstream_decision, "allow");
  assert.equal(authorization.integrity_verified, true);
  assert.equal(authorization.decision_ledger.chain_verified, true);
  assert.equal(authorization.safety.a2_authority_preserved, true);
  assert.equal(authorization.safety.a3_score_recomputed, false);
  assert.equal(authorization.safety.a3_release_ready_recomputed, false);
  assert.equal(authorization.safety.client_chain_verified_flag_trusted_without_recalculation, false);
});

test("A3 live release authorization blocks A2 release_ready=false and stale ledger selectors", async () => {
  const blockedSpine = trustedSpine({ releaseReady: false, decision: "block" });
  const blockedStore = storeWithDecision(blockedSpine);
  const blocked = await blockedStore.authorizeLiveRelease({
    source: "release-source",
    ...scopeOptions(SCOPE),
    enforceScope: true,
    decisionLedgerHeadHash: blockedSpine.decision_ledger.head_hash,
    decisionRecordId: blockedSpine.decision_ledger.records[0].record_id
  });
  assert.equal(blocked.allowed, false);
  assert.equal(blocked.integrity_verified, true);
  assert.ok(blocked.blockers.includes("a2_release_not_ready"));
  assert.ok(blocked.blockers.includes("a2_decision_blocks_release"));

  const allowedSpine = trustedSpine({ releaseReady: true, decision: "allow" });
  const staleStore = storeWithDecision(allowedSpine);
  const stale = await staleStore.authorizeLiveRelease({
    source: "release-source",
    ...scopeOptions(SCOPE),
    enforceScope: true,
    decisionLedgerHeadHash: "sha256:stale",
    decisionRecordId: "sha256:stale"
  });
  assert.equal(stale.allowed, false);
  assert.ok(stale.blockers.includes("decision_head_hash_stale"));
  assert.ok(stale.blockers.includes("decision_record_id_stale"));
});

test("A3 recomputes A2 record, chain, and ledger hashes before live release", async () => {
  const cases = [
    {
      name: "record hash",
      blocker: "decision_record_hash_invalid:0",
      mutate(spine) {
        spine.decision_ledger.records[0].record_hash = `sha256:${"a".repeat(64)}`;
      }
    },
    {
      name: "previous hash",
      blocker: "decision_record_chain_mismatch:0",
      mutate(spine) {
        spine.decision_ledger.records[0].previous_record_hash = `sha256:${"b".repeat(64)}`;
        rehashRecordAndLedger(spine);
      }
    },
    {
      name: "ledger hash",
      blocker: "decision_ledger_hash_invalid",
      mutate(spine) {
        spine.decision_ledger.ledger_hash = `sha256:${"c".repeat(64)}`;
      }
    },
    {
      name: "evidence snapshot hash",
      blocker: "evidence_snapshot_hash_invalid",
      mutate(spine) {
        spine.evidence_snapshot.snapshot_hash = `sha256:${"d".repeat(64)}`;
      }
    }
  ];

  for (const item of cases) {
    const spine = trustedSpine({ releaseReady: true, decision: "allow" });
    item.mutate(spine);
    const store = storeWithDecision(spine);
    const authorization = await store.authorizeLiveRelease({
      source: "release-source",
      ...scopeOptions(SCOPE),
      enforceScope: true,
      decisionLedgerHeadHash: spine.decision_ledger.head_hash,
      decisionRecordId: spine.decision_ledger.records[0].record_id
    });
    assert.equal(authorization.allowed, false, item.name);
    assert.equal(authorization.integrity_verified, false, item.name);
    assert.ok(authorization.blockers.includes(item.blocker), `${item.name}: ${authorization.blockers.join(", ")}`);
  }
});

test("A3 rejects a self-consistent ledger with an unknown decision value", async () => {
  const spine = trustedSpine({ releaseReady: false, decision: "warn" });
  const store = storeWithDecision(spine);
  const authorization = await store.authorizeLiveRelease({
    source: "release-source",
    ...scopeOptions(SCOPE),
    enforceScope: true,
    decisionLedgerHeadHash: spine.decision_ledger.head_hash,
    decisionRecordId: spine.decision_ledger.records[0].record_id
  });

  assert.equal(authorization.allowed, false);
  assert.equal(authorization.integrity_verified, false);
  assert.equal(authorization.upstream_decision, "unknown");
  assert.ok(authorization.blockers.includes("decision_value_invalid:0"));
});

test("direct store live publish fails before transport when A2 Decision Ledger blocks", async () => {
  const spine = trustedSpine({ releaseReady: false, decision: "block" });
  const store = storeWithDecision(spine);
  let transportCalled = false;

  await assert.rejects(
    store.publishGitHubCheckRun({
      source: "release-source",
      ...scopeOptions(SCOPE),
      enforceScope: true,
      repo: "acme/refund-agent",
      headSha: "blocked-head",
      dryRun: false,
      decisionLedgerHeadHash: spine.decision_ledger.head_hash,
      decisionRecordId: spine.decision_ledger.records[0].record_id,
      fetchImpl: async () => {
        transportCalled = true;
        throw new Error("transport must not run");
      }
    }),
    (error) => error instanceof A3StoreValidationError
      && error.statusCode === 403
      && error.error === "a2_release_decision_required"
  );
  assert.equal(transportCalled, false);
  assert.equal(store.exportState().githubPublishReceipts.length, 0);
});

test("self-consistent local A2 allow evidence cannot authorize a live transport", async () => {
  const spine = trustedSpine({ releaseReady: true, decision: "allow" });
  const store = storeWithDecision(spine, { githubExecutorAuthority: "a1_trusted_worker" });
  let transportCalled = false;

  await assert.rejects(
    store.publishGitHubCheckRun({
      source: "release-source",
      ...scopeOptions(SCOPE),
      enforceScope: true,
      repo: "acme/refund-agent",
      headSha: "allowed-but-unattested-head",
      dryRun: false,
      decisionLedgerHeadHash: spine.decision_ledger.head_hash,
      decisionRecordId: spine.decision_ledger.records[0].record_id,
      fetchImpl: async () => {
        transportCalled = true;
        throw new Error("transport must not run");
      }
    }),
    (error) => error instanceof A3StoreValidationError
      && error.statusCode === 403
      && error.error === "a2_trusted_authority_required"
  );
  assert.equal(transportCalled, false);
  assert.equal(store.exportState().githubPublishReceipts.length, 0);
});

function storeWithDecision(spine, options = {}) {
  return createMemoryA3Store({
    ...options,
    sources: {
      "release-source": {
        source: "release-source",
        tenant_scope: SCOPE,
        runFixture: {
          runs: [{
            run_id: "release-run",
            status: "completed",
            cases: [{
              case_id: "release-case",
              status: "passed",
              actual: { final_response: "ok" },
              trace_events: [{ event_type: "agent_response" }]
            }]
          }]
        },
        gradeFixture: {
          grade_results: [{ case_id: "release-case", passed: true, score: 1 }]
        },
        a2TrustedSpine: spine
      }
    }
  });
}

function trustedSpine({ releaseReady, decision }) {
  const evidenceCore = {
    schema_version: "a2.evidence_snapshot.v1",
    ...SCOPE,
    run_id: "release-run",
    case_id: "release-case",
    scenario_id: "refund-release",
    created_at: "2026-07-12T00:00:00Z",
    source_schema_version: "a1.run_fixture.v1",
    source_payload_hash: `sha256:${"1".repeat(64)}`,
    required_modalities: ["text"],
    observed_modalities: ["text"],
    completeness: "complete",
    validation_errors: [],
    missing_modalities: [],
    tool_call_count: 0,
    tool_sequence: [],
    artifacts: [],
    extractor_provenance: [],
    security: {
      tenant_scoped: true,
      scope_complete: true,
      raw_evidence_included: false,
      private_evidence_included: false,
      secrets_included: false,
      artifact_content_included: false
    }
  };
  const evidence = {
    ...evidenceCore,
    snapshot_id: a2CanonicalHash(evidenceCore)
  };
  evidence.snapshot_hash = a2CanonicalHash(evidence);

  const recordCore = {
    schema_version: "a2.decision_record.v1",
    ...SCOPE,
    run_id: evidence.run_id,
    case_id: evidence.case_id,
    scenario_id: evidence.scenario_id,
    created_at: "2026-07-12T00:00:01Z",
    evidence_snapshot_id: evidence.snapshot_id,
    evidence_snapshot_hash: evidence.snapshot_hash,
    evidence_completeness: "complete",
    decision,
    review_required: decision === "review",
    policy_version: "a2.release_policy.v1",
    policy_hash: `sha256:${"2".repeat(64)}`,
    model_versions: ["deterministic:test"],
    judge_versions: ["judge:test"],
    judge_result_hashes: [`sha256:${"3".repeat(64)}`],
    judge_summary: {
      judge_count: 1,
      failed_judges: decision === "block" ? ["judge"] : [],
      abstain_count: 0,
      disagreement: false
    },
    release_gate_hash: `sha256:${"4".repeat(64)}`,
    hard_blockers: decision === "block" ? ["release_gate_blocked"] : [],
    previous_record_hash: GENESIS_HASH,
    public_safe: true
  };
  const record = {
    ...recordCore,
    record_id: a2CanonicalHash(recordCore)
  };
  record.record_hash = a2CanonicalHash(record);

  const ledgerCore = {
    schema_version: "a2.decision_ledger.v1",
    ledger_id: "release-ledger",
    ...SCOPE,
    created_at: "2026-07-12T00:00:02Z",
    record_count: 1,
    genesis_hash: GENESIS_HASH,
    head_hash: record.record_hash,
    records: [record],
    metadata: {
      append_only: true,
      public_safe: true,
      chain_verified: true,
      human_overrides_are_linked_records: true
    }
  };
  const ledger = {
    ...ledgerCore,
    ledger_hash: a2CanonicalHash(ledgerCore)
  };
  return {
    schema_version: "a2.trusted_spine_handoff.v1",
    evidence_snapshot: evidence,
    decision_ledger: ledger,
    a3_consumption: {
      release_ready: releaseReady,
      decision_record_required: true,
      may_recompute_grade: false,
      review_queue_status: releaseReady ? "clear" : "blocked",
      display_decision: decision,
      display_provenance_hash: record.record_hash
    },
    metadata: {
      public_safe: true,
      raw_evidence_included: false,
      secrets_included: false,
      requires_network: false
    }
  };
}

function rehashRecordAndLedger(spine) {
  const record = spine.decision_ledger.records[0];
  record.record_id = a2CanonicalHash(omit(record, ["record_id", "record_hash"]));
  record.record_hash = a2CanonicalHash(omit(record, ["record_hash"]));
  spine.decision_ledger.head_hash = record.record_hash;
  spine.decision_ledger.ledger_hash = a2CanonicalHash(omit(spine.decision_ledger, ["ledger_hash"]));
  spine.a3_consumption.display_provenance_hash = record.record_hash;
}

function omit(value, fields) {
  return Object.fromEntries(Object.entries(value).filter(([key]) => !fields.includes(key)));
}

function scopeOptions(scope) {
  return {
    organizationId: scope.organization_id,
    tenantId: scope.tenant_id,
    workspaceId: scope.workspace_id,
    projectId: scope.project_id,
    environmentId: scope.environment_id
  };
}
