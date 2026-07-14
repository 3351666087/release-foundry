import assert from "node:assert/strict";
import test from "node:test";

import { buildA3DeploymentHandoff } from "../../services/report/a3_deployment_handoff.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

test("rc.2 deployment handoff fails closed when the A2 spine belongs to a different candidate", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["a3-golden-path-rc2"] });
  const dashboard = await store.getDashboardSnapshot("a3-golden-path-rc2");
  const handoff = dashboard.deployment_handoff;

  assert.equal(handoff.schema_version, "a3.deployment_handoff.v1");
  assert.equal(handoff.status, "blocked");
  assert.equal(handoff.production_ready, false);
  assert.equal(handoff.summary.total_checks, 17);
  assert.equal(handoff.summary.passed, 8);
  assert.equal(handoff.summary.blocked_or_not_proven, 9);
  assert.equal(handoff.summary.owner_group_count, 5);
  assert.equal(handoff.summary.golden_path_passed, 7);
  assert.equal(handoff.summary.golden_path_total, 11);

  assert.equal(handoff.candidate_binding.status, "integrity_invalid");
  assert.equal(handoff.candidate_binding.same_candidate_bound, false);
  assert.equal(handoff.candidate_binding.expected.run_id, "a3-golden-20260712-002");
  assert.equal(handoff.candidate_binding.observed_a2.evidence_run_id, "a2_trusted_spine_demo");
  assert.equal(handoff.candidate_binding.runtime_authority.status, "integrity_invalid");
  assert.equal(handoff.candidate_binding.runtime_authority.upstream_decision, "unknown");
  assert.equal(handoff.candidate_binding.historical_packet.decision, "block");

  assert.deepEqual(
    handoff.owner_groups.map((group) => group.owner),
    ["A2", "A1", "A1/A3", "A3", "Repository maintainer"]
  );
  assert.equal(handoff.blocking_items.length, 9);
  assert.equal(handoff.blocking_items.some((item) => item.id === "a2_release_authority"), true);
  assert.equal(handoff.blocking_items.some((item) => item.id === "github_app_installation"), true);
  assert.equal(handoff.blocking_items.some((item) => item.id === "required_check_enforcement"), true);
  assert.equal(handoff.safety.a2_decision_recomputed, false);
  assert.equal(handoff.safety.historical_packet_treated_as_current_authority, false);
});

test("deployment handoff becomes ready only when checks pass and one candidate is bound end to end", () => {
  const scope = {
    organization_id: "org-one",
    tenant_id: "tenant-one",
    workspace_id: "workspace-one",
    project_id: "project-one",
    environment_id: "staging"
  };
  const handoff = buildA3DeploymentHandoff({
    deploymentAcceptance: {
      checks: [{
        id: "release_artifact_verification",
        label: "Artifact verified",
        owner: "A3",
        status: "passed",
        evidence_class: "local_verification",
        production_proof: false
      }]
    },
    deliveryGoldenPath: {
      run_ids: ["run-one"],
      progress: { passed: 11, total: 11 },
      authoritative_release: { integrity_verified: true, upstream_decision: "allow", release_ready: true }
    },
    trustedReleaseAuthority: {
      integrity_verified: true,
      status: "release_ready",
      upstream_decision: "allow",
      release_ready: true,
      reason_code: "a2_release_ready"
    },
    a2TrustedSpine: {
      evidence_snapshot: { ...scope, run_id: "run-one", snapshot_id: "snapshot-one" },
      decision_ledger: {
        head_hash: "sha256:ledger-one",
        records: [{ ...scope, run_id: "run-one", record_id: "record-one" }]
      }
    },
    runFixture: { runs: [{ run_id: "run-one" }] },
    releaseArtifactManifest: {
      release: { version: "1.0.0", run_ids: ["run-one"], git_sha_alias: "candidate-one" }
    }
  }, {
    source: "candidate-one",
    tenantScope: scope
  });

  assert.equal(handoff.candidate_binding.same_candidate_bound, true);
  assert.equal(handoff.candidate_binding.status, "bound");
  assert.equal(handoff.status, "ready");
  assert.equal(handoff.summary.blocked_or_not_proven, 0);
  assert.equal(handoff.next_actions.length, 0);
});
