import { createHash } from "node:crypto";

const A2_SCOPE_FIELDS = Object.freeze([
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
]);
const A2_GENESIS_HASH = `sha256:${"0".repeat(64)}`;
const A2_VALID_DECISIONS = new Set(["allow", "block", "review"]);
const A2_VALID_COMPLETENESS = new Set(["complete", "partial", "evidence_missing", "invalid"]);
const A2_LEGACY_SPINE_SCHEMA = "a2.trusted_spine_handoff.v1";
const A2_CANDIDATE_SPINE_SCHEMA = "a2.candidate_trusted_spine.v1";

export function evaluateA2TrustedReleaseAuthority(spine = {}, options = {}) {
  const integrity = verifyA2TrustedSpine(spine, options);
  const consumption = objectOr(spine.a3_consumption);
  const trustedDecision = integrity.integrity_verified ? integrity.latest_record.decision : "unknown";
  const releaseBlockers = [...integrity.integrity_blockers];

  if (integrity.integrity_verified) {
    if (trustedDecision !== "allow") releaseBlockers.push("a2_decision_blocks_release");
    if (consumption.release_ready !== true) releaseBlockers.push("a2_release_not_ready");
    if (integrity.latest_record.review_required === true) releaseBlockers.push("a2_review_required");
    if (integrity.latest_record.evidence_completeness !== "complete") releaseBlockers.push("evidence_incomplete");
    if (Array.isArray(integrity.latest_record.hard_blockers) && integrity.latest_record.hard_blockers.length > 0) {
      releaseBlockers.push("a2_hard_blockers_present");
    }
    if (Number(integrity.latest_record.judge_summary?.abstain_count || 0) > 0) {
      releaseBlockers.push("a2_judge_abstention_present");
    }
  }

  const expectedHeadHash = options.expectedHeadHash || options.decisionLedgerHeadHash || options.decision_ledger_head_hash;
  const expectedRecordId = options.expectedRecordId || options.decisionRecordId || options.decision_record_id;
  if (options.requireSelectors === true) {
    if (!expectedHeadHash) releaseBlockers.push("decision_head_hash_required");
    else if (expectedHeadHash !== integrity.ledger.head_hash) releaseBlockers.push("decision_head_hash_stale");
    if (!expectedRecordId) releaseBlockers.push("decision_record_id_required");
    else if (expectedRecordId !== integrity.latest_record.record_id) releaseBlockers.push("decision_record_id_stale");
  }

  const blockers = [...new Set(releaseBlockers)];
  const releaseReady = integrity.integrity_verified
    && trustedDecision === "allow"
    && consumption.release_ready === true
    && integrity.latest_record.review_required !== true
    && integrity.latest_record.evidence_completeness === "complete"
    && (!Array.isArray(integrity.latest_record.hard_blockers) || integrity.latest_record.hard_blockers.length === 0)
    && Number(integrity.latest_record.judge_summary?.abstain_count || 0) === 0;
  const allowed = releaseReady && blockers.length === 0;

  return {
    schema_version: "a3.trusted_release_authority.v1",
    integrity_verified: integrity.integrity_verified,
    allowed,
    status: authorityStatus(integrity.integrity_verified, trustedDecision, releaseReady),
    decision: allowed ? "allowed_by_a2_decision_ledger" : "denied_by_a2_decision_ledger",
    reason_code: blockers[0] || "none",
    blockers,
    integrity_blockers: integrity.integrity_blockers,
    release_ready: releaseReady,
    upstream_decision: trustedDecision,
    decision_ledger: {
      schema_version: integrity.ledger.schema_version || "missing",
      ledger_id: integrity.ledger.ledger_id || null,
      head_hash: integrity.ledger.head_hash || null,
      ledger_hash: integrity.ledger.ledger_hash || null,
      record_count: Number.isInteger(integrity.ledger.record_count) ? integrity.ledger.record_count : null,
      record_id: integrity.latest_record.record_id || null,
      record_hash: integrity.latest_record.record_hash || null,
      chain_verified: integrity.integrity_verified
    },
    evidence_snapshot: {
      schema_version: integrity.evidence.schema_version || "missing",
      snapshot_id: integrity.evidence.snapshot_id || null,
      snapshot_hash: integrity.evidence.snapshot_hash || null,
      completeness: integrity.evidence.completeness || "unknown"
    },
    safety: {
      a2_authority_preserved: true,
      a3_score_recomputed: false,
      a3_release_ready_recomputed: false,
      client_chain_verified_flag_trusted_without_recalculation: false,
      raw_evidence_included: false,
      secret_values_allowed: false
    }
  };
}

export function verifyA2TrustedSpine(spine = {}, options = {}) {
  const integrityBlockers = [];
  const add = (reason) => integrityBlockers.push(reason);
  const legacySpine = spine.schema_version === A2_LEGACY_SPINE_SCHEMA;
  const candidateSpine = spine.schema_version === A2_CANDIDATE_SPINE_SCHEMA;
  const evidenceSnapshots = candidateSpine
    ? arrayOf(spine.evidence_snapshots).map(objectOr)
    : [objectOr(spine.evidence_snapshot)];
  const ledger = objectOr(spine.decision_ledger);
  const records = Array.isArray(ledger.records) ? ledger.records.map(objectOr) : [];
  const latestRecord = records.at(-1) || {};
  const expectedScope = normalizeExpectedScope(options.expectedScope || options.scope || {});

  if (!legacySpine && !candidateSpine) add("trusted_spine_missing");
  if (!evidenceSnapshots.length || evidenceSnapshots.some((item) => !Object.keys(item).length)) {
    add("evidence_snapshot_missing");
  }
  evidenceSnapshots.forEach((evidence, index) => {
    const suffix = candidateSpine ? `:${index}` : "";
    if (evidence.schema_version !== "a2.evidence_snapshot.v1") add(`evidence_snapshot_missing${suffix}`);
    if (!scopeComplete(evidence)) add(`evidence_scope_incomplete${suffix}`);
    if (scopeComplete(expectedScope) && !scopesEqual(evidence, expectedScope)) add(`evidence_scope_mismatch${suffix}`);
    if (evidence.snapshot_id !== hashWithout(evidence, ["snapshot_id", "snapshot_hash"])) add(`evidence_snapshot_id_invalid${suffix}`);
    if (evidence.snapshot_hash !== hashWithout(evidence, ["snapshot_hash"])) add(`evidence_snapshot_hash_invalid${suffix}`);
    if (!A2_VALID_COMPLETENESS.has(evidence.completeness) || evidence.security?.scope_complete !== true) {
      add(`evidence_contract_invalid${suffix}`);
    }
    if (legacySpine && evidence.completeness !== "complete") add("evidence_incomplete");
    if (
      evidence.security?.secrets_included === true
      || evidence.security?.raw_evidence_included === true
      || evidence.security?.private_evidence_included === true
      || evidence.security?.artifact_content_included === true
    ) add(`evidence_not_public_safe${suffix}`);
  });

  if (ledger.schema_version !== "a2.decision_ledger.v1") add("decision_ledger_missing");
  if (!scopeComplete(ledger)) add("decision_ledger_scope_incomplete");
  if (scopeComplete(expectedScope) && !scopesEqual(ledger, expectedScope)) add("decision_scope_mismatch");
  if (ledger.genesis_hash !== A2_GENESIS_HASH) add("decision_ledger_genesis_invalid");
  if (ledger.metadata?.append_only !== true) add("decision_ledger_not_append_only");
  if (ledger.metadata?.chain_verified !== true) add("decision_ledger_chain_marker_missing");
  if (ledger.metadata?.public_safe !== true) add("decision_ledger_not_public_safe");
  if (!records.length || !Number.isInteger(ledger.record_count) || ledger.record_count !== records.length) {
    add("decision_record_count_invalid");
  }

  let previousHash = A2_GENESIS_HASH;
  records.forEach((record, index) => {
    if (record.schema_version !== "a2.decision_record.v1") add(`decision_record_schema_invalid:${index}`);
    if (!scopeComplete(record) || !scopesEqual(record, ledger)) add(`decision_record_scope_mismatch:${index}`);
    if (scopeComplete(expectedScope) && !scopesEqual(record, expectedScope)) add(`decision_record_request_scope_mismatch:${index}`);
    if (record.previous_record_hash !== previousHash) add(`decision_record_chain_mismatch:${index}`);
    if (record.record_id !== hashWithout(record, ["record_id", "record_hash"])) add(`decision_record_id_invalid:${index}`);
    if (record.record_hash !== hashWithout(record, ["record_hash"])) add(`decision_record_hash_invalid:${index}`);
    if (!A2_VALID_DECISIONS.has(record.decision)) add(`decision_value_invalid:${index}`);
    if (record.public_safe !== true) add(`decision_record_not_public_safe:${index}`);
    const linkedEvidence = evidenceSnapshots.find((item) => (
      item.snapshot_id === record.evidence_snapshot_id
      && item.snapshot_hash === record.evidence_snapshot_hash
    ));
    if (!linkedEvidence) {
      add(`evidence_snapshot_mismatch:${index}`);
    } else {
      for (const field of ["run_id", "case_id", "scenario_id"]) {
        if (String(record[field] || "") !== String(linkedEvidence[field] || "")) add(`evidence_${field}_mismatch:${index}`);
      }
      if (record.evidence_completeness !== linkedEvidence.completeness) add(`evidence_completeness_mismatch:${index}`);
      if (record.decision === "allow" && linkedEvidence.completeness !== "complete") add(`allow_with_incomplete_evidence:${index}`);
    }
    previousHash = typeof record.record_hash === "string" ? record.record_hash : "";
  });

  if (ledger.head_hash !== previousHash) add("decision_ledger_head_invalid");
  if (ledger.ledger_hash !== hashWithout(ledger, ["ledger_hash"])) add("decision_ledger_hash_invalid");

  const evidence = evidenceSnapshots.find((item) => (
    item.snapshot_id === latestRecord.evidence_snapshot_id
    && item.snapshot_hash === latestRecord.evidence_snapshot_hash
  )) || evidenceSnapshots.at(-1) || {};

  if (candidateSpine) {
    const binding = objectOr(spine.candidate_binding);
    if (!binding.candidate_id || !binding.run_id || !binding.evidence_release_version) add("candidate_binding_incomplete");
    if (binding.run_id && evidenceSnapshots.some((item) => item.run_id !== binding.run_id)) add("candidate_run_id_mismatch");
    if (binding.run_id && records.some((item) => item.run_id !== binding.run_id)) add("candidate_ledger_run_id_mismatch");
    if (!/^sha256:[0-9a-f]{64}$/.test(String(binding.a1_evidence_bundle_hash || ""))) add("candidate_a1_evidence_hash_invalid");
    if (!/^[0-9a-f]{40}$/.test(String(binding.a1_source_commit || ""))) add("candidate_a1_source_commit_invalid");
    if (!/^[0-9a-f]{40}$/.test(String(binding.a2_authority_commit || ""))) add("candidate_a2_authority_commit_invalid");
    if (!/^sha256:[0-9a-f]{64}$/.test(String(spine.grade_results?.hash || ""))) add("candidate_grades_hash_invalid");
  }

  const consumption = objectOr(spine.a3_consumption);
  if (consumption.decision_record_required !== true || consumption.may_recompute_grade !== false) {
    add("a3_consumption_contract_invalid");
  }
  if (consumption.display_decision !== latestRecord.decision) add("display_decision_mismatch");
  if (consumption.display_provenance_hash !== latestRecord.record_hash) add("display_provenance_hash_mismatch");
  if (consumption.release_ready === true && latestRecord.decision !== "allow") add("release_ready_decision_mismatch");
  if (spine.metadata?.public_safe !== true || spine.metadata?.secrets_included === true) add("trusted_spine_not_public_safe");

  const uniqueBlockers = [...new Set(integrityBlockers)];
  return {
    schema_version: "a3.a2_trusted_spine_verification.v1",
    integrity_verified: uniqueBlockers.length === 0,
    integrity_blockers: uniqueBlockers,
    evidence,
    evidence_snapshots: evidenceSnapshots,
    ledger,
    latest_record: latestRecord,
    candidate_binding: candidateSpine ? objectOr(spine.candidate_binding) : null
  };
}

export function a2CanonicalHash(value) {
  const canonical = JSON.stringify(sortForCanonicalJson(value)).replace(/[\u007f-\uffff]/g, (character) => (
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
  ));
  return `sha256:${createHash("sha256").update(canonical, "utf8").digest("hex")}`;
}

function hashWithout(value, omittedFields) {
  const payload = Object.fromEntries(
    Object.entries(objectOr(value)).filter(([key]) => !omittedFields.includes(key))
  );
  return a2CanonicalHash(payload);
}

function sortForCanonicalJson(value) {
  if (Array.isArray(value)) return value.map(sortForCanonicalJson);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort((left, right) => left < right ? -1 : left > right ? 1 : 0)
        .map((key) => [key, sortForCanonicalJson(value[key])])
    );
  }
  return value;
}

function normalizeExpectedScope(value = {}) {
  const nested = objectOr(value.tenant_scope || value.tenantScope);
  return Object.fromEntries(A2_SCOPE_FIELDS.map((field) => {
    const camel = field.replace(/_([a-z])/g, (_, character) => character.toUpperCase());
    return [field, value[field] ?? value[camel] ?? nested[field] ?? nested[camel] ?? ""];
  }));
}

function scopeComplete(value = {}) {
  return A2_SCOPE_FIELDS.every((field) => String(value[field] ?? "").length > 0);
}

function scopesEqual(left = {}, right = {}) {
  return A2_SCOPE_FIELDS.every((field) => String(left[field] ?? "") === String(right[field] ?? ""));
}

function authorityStatus(integrityVerified, decision, releaseReady) {
  if (!integrityVerified) return "integrity_invalid";
  if (releaseReady) return "release_ready";
  if (decision === "block") return "blocked";
  if (decision === "review") return "review_required";
  return "not_ready";
}

function objectOr(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function arrayOf(value) {
  return Array.isArray(value) ? value : [];
}
