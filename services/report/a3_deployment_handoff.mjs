export const A3_DEPLOYMENT_HANDOFF_SCHEMA_VERSION = "a3.deployment_handoff.v1";

const OWNER_GROUPS = Object.freeze([
  { id: "decision_authority", owner: "A2", label: "Decision authority", dependency: "upstream_authority" },
  { id: "runtime_identity", owner: "A1", label: "Runtime and identity", dependency: "upstream_runtime" },
  { id: "platform_delivery", owner: "A1/A3", label: "Platform delivery", dependency: "shared_delivery" },
  { id: "product_evidence", owner: "A3", label: "Product and evidence", dependency: "a3_owned" },
  { id: "repository_governance", owner: "Repository maintainer", label: "Repository governance", dependency: "external_governance" }
]);

const ACTIONS = Object.freeze({
  a2_release_authority: [
    "Issue an A2 Trusted Spine for the exact candidate scope and run, then attach its immutable ledger selectors.",
    "A2 evidence snapshot, Decision Ledger record, head hash, record id, and candidate scope receipt"
  ],
  hosted_identity: [
    "Deploy the A1 identity verifier in the target environment and read back its service identity and version.",
    "deployment identity, verifier version, issuer/audience policy, and sanitized health receipt"
  ],
  postgres_rls: [
    "Run migrations against target PostgreSQL and prove tenant isolation through live RLS denial and allow checks.",
    "database identity, migration version, schema digest, RLS allow/deny receipts, and backup marker"
  ],
  queue_worker: [
    "Deploy the durable worker and exercise enqueue, retry, dead-letter, lease recovery, and worker health.",
    "queue identity, worker version, retry/dead-letter receipt, lease recovery, and queue depth health"
  ],
  object_storage: [
    "Write the Audit Bundle to immutable object storage and verify readback, retention, and tenant scope.",
    "object version, content digest, retention policy, tenant scope, and readback verification"
  ],
  deployment_health: [
    "Deploy the candidate to staging or VPC and read back identity, image, config, migration, health, and network policy.",
    "deployment id, image digest, config digest, migration id, health endpoints, tenant isolation, and network receipt"
  ],
  upgrade_rollback: [
    "Rehearse install, upgrade, injected failure, rollback, backup, restore, and post-restore health on the deployed target.",
    "upgrade plan, failure trigger, rollback id, backup id, restore id, duration, and final health receipt"
  ],
  github_app_installation: [
    "Install a tenant-bound custom GitHub App and execute the release operation through that installation identity.",
    "tenant id, installation alias, app slug, permission set, repository binding, and Check readback"
  ],
  required_check_enforcement: [
    "Enable the approved required Check on main and prove that a failing candidate cannot merge.",
    "branch policy readback, required context, failing merge denial, and maintainer approval reference"
  ]
});

export function buildA3DeploymentHandoff(inputs = {}, options = {}) {
  const acceptance = object(inputs.deploymentAcceptance || inputs.deployment_acceptance);
  const path = object(inputs.deliveryGoldenPath || inputs.delivery_golden_path);
  const authority = object(inputs.trustedReleaseAuthority || inputs.trusted_release_authority);
  const spine = object(inputs.a2TrustedSpine || inputs.a2_trusted_spine);
  const run = firstRun(object(inputs.runFixture || inputs.run_fixture));
  const manifest = object(inputs.releaseArtifactManifest || inputs.release_artifact_manifest);
  const release = object(manifest.release);
  const expectedScope = normalizeScope(options.tenantScope || options.tenant_scope || {});
  const evidence = object(spine.evidence_snapshot);
  const ledger = object(spine.decision_ledger);
  const decisionRecord = list(ledger.records).map(object).at(-1) || {};
  const expectedRunId = text(run.run_id, "unknown");
  const observedRunId = text(evidence.run_id, "unknown");
  const scopeMatches = scopeComplete(expectedScope) && scopesEqual(expectedScope, evidence);
  const runMatches = expectedRunId !== "unknown" && observedRunId === expectedRunId;
  const artifactRunBound = list(release.run_ids).map(String).includes(expectedRunId);
  const goldenPathRunBound = list(path.run_ids).map(String).includes(expectedRunId);
  const decisionRunBound = text(decisionRecord.run_id, "unknown") === expectedRunId;
  const authorityIntegrityVerified = authority.integrity_verified === true;
  const checks = list(acceptance.checks).map((item) => normalizeCheck(item, authority));
  const groups = OWNER_GROUPS.map((group) => ownerGroup(group, checks));
  const blockers = checks.filter((check) => check.status !== "passed");
  const productionProofCount = checks.filter((check) => check.production_proof).length;
  const candidateBinding = {
    schema_version: "a3.candidate_binding_handoff.v1",
    status: authorityIntegrityVerified && scopeMatches && runMatches && artifactRunBound && goldenPathRunBound && decisionRunBound
      ? "bound"
      : "integrity_invalid",
    same_candidate_bound: authorityIntegrityVerified
      && scopeMatches
      && runMatches
      && artifactRunBound
      && goldenPathRunBound
      && decisionRunBound,
    expected: {
      source: text(options.source, "unknown"),
      tenant_scope: expectedScope,
      run_id: expectedRunId,
      release_version: text(release.version, text(path.release_version, "unknown")),
      candidate_sha_alias: release.git_sha_alias || null
    },
    observed_a2: {
      tenant_scope: normalizeScope(evidence),
      evidence_run_id: observedRunId,
      decision_run_id: text(decisionRecord.run_id, "unknown"),
      evidence_snapshot_id: evidence.snapshot_id || null,
      decision_record_id: decisionRecord.record_id || null,
      decision_ledger_head_hash: ledger.head_hash || null
    },
    checks: [
      bindingCheck("tenant_scope", scopeMatches, "A2 evidence and ledger must use the exact requested five-level tenant scope."),
      bindingCheck("run_id", runMatches && decisionRunBound, "A2 evidence and decision must bind the exact A1 run id."),
      bindingCheck("release_artifact_run", artifactRunBound, "Release Artifact run_ids must include the exact A1 run."),
      bindingCheck("golden_path_run", goldenPathRunBound, "Golden Path run_ids must include the exact A1 run."),
      bindingCheck("a2_integrity", authorityIntegrityVerified, "The backend A2 Trusted Spine verifier must pass scope, chain, and hash validation.")
    ],
    runtime_authority: {
      status: text(authority.status, authorityIntegrityVerified ? "not_ready" : "integrity_invalid"),
      integrity_verified: authorityIntegrityVerified,
      upstream_decision: authorityIntegrityVerified ? text(authority.upstream_decision, "unknown") : "unknown",
      release_ready: authorityIntegrityVerified && authority.release_ready === true,
      reason_code: text(authority.reason_code, "trusted_authority_missing"),
      blockers: list(authority.blockers).map((item) => text(item, "")).filter(Boolean)
    },
    historical_packet: {
      integrity_marker: object(path.authoritative_release).integrity_verified === true,
      decision: text(object(path.authoritative_release).upstream_decision, "unknown"),
      release_ready: object(path.authoritative_release).release_ready === true
    },
    next_action_owner: "A2 + A3",
    next_action: "Generate a new A2 Trusted Spine for this exact run and scope, then rebuild the A3 candidate artifact with immutable ledger selectors."
  };

  return {
    schema_version: A3_DEPLOYMENT_HANDOFF_SCHEMA_VERSION,
    source: text(options.source, "unknown"),
    status: !candidateBinding.same_candidate_bound || blockers.length ? "blocked" : "ready",
    production_ready: false,
    summary: {
      total_checks: checks.length,
      passed: checks.filter((check) => check.status === "passed").length,
      blocked_or_not_proven: blockers.length,
      production_proof_count: productionProofCount,
      owner_group_count: groups.length,
      candidate_binding_status: candidateBinding.status,
      golden_path_passed: integer(object(path.progress).passed),
      golden_path_total: integer(object(path.progress).total)
    },
    candidate_binding: candidateBinding,
    owner_groups: groups,
    blocking_items: blockers,
    next_actions: [
      ...(candidateBinding.same_candidate_bound ? [] : [{
        id: "candidate_binding",
        owner: candidateBinding.next_action_owner,
        action: candidateBinding.next_action,
        required_receipt: "run-bound A2 evidence snapshot, Decision Ledger selectors, scope receipt, candidate SHA, and rebuilt artifact manifest"
      }]),
      ...blockers.map((check) => ({
        id: check.id,
        owner: check.owner,
        action: check.next_action,
        required_receipt: check.required_receipt
      }))
    ],
    safety: {
      source_status_overridden: false,
      a2_decision_recomputed: false,
      a2_release_ready_recomputed: false,
      historical_packet_treated_as_current_authority: false,
      contract_only_claimed_as_production: false,
      secret_values_allowed: false
    }
  };
}

function normalizeCheck(value, authority) {
  const check = object(value);
  const action = ACTIONS[check.id] || [
    "Attach a current authoritative receipt for this check.",
    "versioned, scoped, timestamped, and sanitized verification receipt"
  ];
  const authorityInvalid = check.id === "a2_release_authority" && authority.integrity_verified !== true;
  const status = authorityInvalid ? "blocked" : text(check.status, "not_proven");
  return {
    id: text(check.id),
    label: text(check.label, text(check.id)),
    owner: text(check.owner, "Unassigned"),
    status,
    evidence_class: authorityInvalid ? "integrity_invalid" : text(check.evidence_class, "not_proven"),
    evidence_level: evidenceLevel(status, authorityInvalid ? "integrity_invalid" : check.evidence_class, check.production_proof === true),
    production_proof: check.production_proof === true,
    evidence_ref: check.evidence_ref || null,
    blocked_reason: authorityInvalid
      ? text(authority.reason_code, "trusted_authority_integrity_invalid")
      : check.blocked_reason || null,
    next_action: action[0],
    required_receipt: action[1]
  };
}

function ownerGroup(group, checks) {
  const owned = checks.filter((check) => check.owner === group.owner);
  const blocked = owned.filter((check) => check.status !== "passed");
  return {
    id: group.id,
    owner: group.owner,
    label: group.label,
    dependency: group.dependency,
    status: blocked.length ? "blocked" : "passed",
    total: owned.length,
    passed: owned.length - blocked.length,
    blocked: blocked.length,
    production_proof_count: owned.filter((check) => check.production_proof).length,
    actionable_by_a3: group.owner === "A3" || group.owner === "A1/A3",
    blocking_ids: blocked.map((check) => check.id),
    checks: owned
  };
}

function evidenceLevel(status, evidenceClass, productionProof) {
  if (status !== "passed") return evidenceClass === "contract_only" ? "contract_only" : "not_proven";
  if (productionProof) return "production_verified";
  if (evidenceClass === "local_authoritative") return "locally_authoritative";
  return "locally_verified";
}

function bindingCheck(id, passed, requirement) {
  return { id, status: passed ? "passed" : "failed", passed, requirement };
}

function firstRun(runFixture) {
  return object(list(runFixture.runs)[0] || runFixture);
}

function normalizeScope(value) {
  const nested = object(value.tenant_scope || value.tenantScope);
  return {
    organization_id: text(value.organization_id ?? value.organizationId ?? nested.organization_id, ""),
    tenant_id: text(value.tenant_id ?? value.tenantId ?? nested.tenant_id, ""),
    workspace_id: text(value.workspace_id ?? value.workspaceId ?? nested.workspace_id, ""),
    project_id: text(value.project_id ?? value.projectId ?? nested.project_id, ""),
    environment_id: text(value.environment_id ?? value.environmentId ?? nested.environment_id, "")
  };
}

function scopeComplete(value) {
  return Object.values(value).every((item) => Boolean(item));
}

function scopesEqual(left, right) {
  return Object.keys(left).every((key) => left[key] === right[key]);
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function text(value, fallback = "unknown") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function integer(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : fallback;
}
