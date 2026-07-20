import { a2CanonicalHash, evaluateA2TrustedReleaseAuthority, verifyA2TrustedSpine } from "./a3_trusted_release_authority.mjs";

export const A3_CANDIDATE_DELIVERY_BINDING_SCHEMA_VERSION = "a3.candidate_delivery_binding.v1";
export const A3_SHARED_CANDIDATE_IDENTITY_SCHEMA_VERSION = "a2.shared_candidate_identity.v2";

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/;

export function buildA3SharedCandidateIdentity(input = {}, options = {}) {
  const sourceIdentity = object(input.a2SharedIdentity);
  const spine = object(input.a2TrustedSpine);
  const binding = object(spine.candidate_binding);
  const ledger = object(spine.decision_ledger);
  const gradeResults = object(spine.grade_results);
  const a3GitSha = options.a3GitSha || input.a3GitSha;
  const identity = {
    ...sourceIdentity,
    a3: {
      ...object(sourceIdentity.a3),
      candidate_id: binding.candidate_id || sourceIdentity.candidate_id,
      git_sha: a3GitSha,
      consumed_decision_hash: ledger.head_hash,
      consumed_grades_hash: gradeResults.hash
    },
    binding_state: "exact",
    blockers: [],
    release_authority: false,
    public_safe: true
  };
  const verification = verifyA3SharedCandidateIdentity(identity, {
    ...options,
    a2SourceIdentity: sourceIdentity,
    a2TrustedSpine: spine,
    runFixture: input.runFixture
  });
  if (!verification.verified) {
    throw new Error(`A3 shared candidate identity is invalid: ${verification.blockers.join(", ")}`);
  }
  return identity;
}

export function verifyA3SharedCandidateIdentity(identity = {}, options = {}) {
  const blockers = [];
  const add = (reason) => blockers.push(reason);
  const a1 = object(identity.a1);
  const a2 = object(identity.a2);
  const a3 = object(identity.a3);
  const sourceIdentity = object(options.a2SourceIdentity);
  const spine = object(options.a2TrustedSpine);
  const binding = object(spine.candidate_binding);
  const ledger = object(spine.decision_ledger);
  const gradeResults = object(spine.grade_results);
  const runFixture = object(options.runFixture);

  if (identity.schema_version !== A3_SHARED_CANDIDATE_IDENTITY_SCHEMA_VERSION) add("shared_identity_schema_invalid");
  const candidateIds = [identity.candidate_id, a1.candidate_id, a2.candidate_id, a3.candidate_id].filter(Boolean);
  if (candidateIds.length !== 4 || new Set(candidateIds).size !== 1) add("shared_candidate_id_mismatch");
  if (!GIT_SHA_PATTERN.test(String(a1.git_sha || ""))) add("a1_git_sha_invalid");
  if (!GIT_SHA_PATTERN.test(String(a2.git_sha || ""))) add("a2_git_sha_invalid");
  if (!GIT_SHA_PATTERN.test(String(a3.git_sha || ""))) add("a3_git_sha_invalid");
  if (!SHA256_PATTERN.test(String(a1.evidence_bundle_hash || ""))) add("a1_evidence_bundle_hash_invalid");
  if (!SHA256_PATTERN.test(String(a2.decision_hash || ""))) add("a2_decision_hash_invalid");
  if (!SHA256_PATTERN.test(String(a2.grades_hash || ""))) add("a2_grades_hash_invalid");
  if (a2.decision_hash !== a3.consumed_decision_hash) add("a3_consumed_decision_hash_mismatch");
  if (a2.grades_hash !== a3.consumed_grades_hash) add("a3_consumed_grades_hash_mismatch");
  if (identity.binding_state !== "exact" || array(identity.blockers).length > 0) add("a3_binding_not_exact");
  if (identity.release_authority !== false) add("a3_release_authority_claimed");
  if (identity.public_safe !== true) add("shared_identity_not_public_safe");

  if (Object.keys(sourceIdentity).length) {
    if (sourceIdentity.schema_version !== identity.schema_version) add("a2_source_identity_schema_mismatch");
    if (sourceIdentity.candidate_id !== identity.candidate_id) add("a2_source_candidate_id_mismatch");
    if (a2CanonicalHash(sourceIdentity.a1) !== a2CanonicalHash(a1)) add("a1_source_binding_changed");
    if (a2CanonicalHash(sourceIdentity.a2) !== a2CanonicalHash(a2)) add("a2_source_binding_changed");
  }

  if (Object.keys(spine).length) {
    const spineVerification = verifyA2TrustedSpine(spine);
    if (!spineVerification.integrity_verified) add("a2_trusted_spine_invalid");
    if (binding.candidate_id !== identity.candidate_id) add("spine_candidate_id_mismatch");
    if (binding.a1_source_commit !== a1.git_sha) add("spine_a1_source_commit_mismatch");
    if (binding.a1_evidence_bundle_hash !== a1.evidence_bundle_hash) add("spine_a1_evidence_hash_mismatch");
    if (binding.a2_authority_commit !== a2.git_sha) add("spine_a2_authority_commit_mismatch");
    if (ledger.head_hash !== a3.consumed_decision_hash) add("spine_decision_hash_mismatch");
    if (gradeResults.hash !== a3.consumed_grades_hash) add("spine_grades_hash_mismatch");
    if (options.releaseVersion && binding.evidence_release_version !== options.releaseVersion) add("release_version_mismatch");
  }
  if (runFixture.run_id && binding.run_id && runFixture.run_id !== binding.run_id) add("run_id_mismatch");
  if (options.a3GitSha && a3.git_sha !== options.a3GitSha) add("a3_git_sha_mismatch");

  const uniqueBlockers = [...new Set(blockers)].sort();
  return {
    schema_version: "a3.shared_candidate_identity_verification.v1",
    verified: uniqueBlockers.length === 0,
    binding_state: uniqueBlockers.length === 0 ? "exact" : "invalid",
    candidate_id: identity.candidate_id || null,
    run_id: binding.run_id || runFixture.run_id || null,
    release_version: binding.evidence_release_version || options.releaseVersion || null,
    consumed_decision_hash: a3.consumed_decision_hash || null,
    consumed_grades_hash: a3.consumed_grades_hash || null,
    a3_git_sha: a3.git_sha || null,
    blockers: uniqueBlockers
  };
}

export function buildA3CandidateDeliveryBinding(input = {}, options = {}) {
  const identity = object(input.a3SharedIdentity);
  const spine = object(input.a2TrustedSpine);
  const runFixture = object(input.runFixture);
  const binding = object(spine.candidate_binding);
  const authority = evaluateA2TrustedReleaseAuthority(spine);
  const identityVerification = verifyA3SharedCandidateIdentity(identity, {
    a2SourceIdentity: input.a2SharedIdentity,
    a2TrustedSpine: spine,
    runFixture,
    releaseVersion: options.releaseVersion,
    a3GitSha: options.a3GitSha
  });
  if (!identityVerification.verified) {
    throw new Error(`A3 candidate delivery identity is invalid: ${identityVerification.blockers.join(", ")}`);
  }
  const core = {
    schema_version: A3_CANDIDATE_DELIVERY_BINDING_SCHEMA_VERSION,
    generated_at: options.generatedAt || "runtime",
    candidate: {
      candidate_id: binding.candidate_id,
      run_id: binding.run_id,
      release_version: binding.evidence_release_version
    },
    upstream: {
      a1_source_commit: binding.a1_source_commit,
      a1_evidence_bundle_hash: binding.a1_evidence_bundle_hash,
      a2_authority_commit: binding.a2_authority_commit,
      a2_decision_ledger_head_hash: spine.decision_ledger?.head_hash,
      a2_grades_hash: spine.grade_results?.hash,
      a2_upstream_decision: authority.upstream_decision,
      a2_release_ready: authority.release_ready
    },
    a3: {
      implementation_commit: identity.a3?.git_sha,
      consumed_decision_ledger_head_hash: identity.a3?.consumed_decision_hash,
      consumed_grades_hash: identity.a3?.consumed_grades_hash,
      delivery_status: authority.allowed ? "pending_delivery_acceptance" : "blocked_by_a2",
      production_ready: false,
      a2_decision_recomputed: false
    },
    shared_identity_hash: a2CanonicalHash(identity),
    binding_state: "exact",
    blockers: [],
    release_blockers: array(authority.blockers),
    safety: {
      a2_authority_preserved: true,
      a3_release_authority_claimed: false,
      human_approval_claimed: false,
      production_authority_claimed: false,
      secrets_included: false,
      public_safe: true
    }
  };
  const result = { ...core, binding_hash: a2CanonicalHash(core) };
  const verification = verifyA3CandidateDeliveryBinding(result, {
    ...options,
    a2SourceIdentity: input.a2SharedIdentity,
    a3SharedIdentity: identity,
    a2TrustedSpine: spine,
    runFixture
  });
  if (!verification.verified) {
    throw new Error(`A3 candidate delivery binding is invalid: ${verification.blockers.join(", ")}`);
  }
  return result;
}

export function verifyA3CandidateDeliveryBinding(value = {}, options = {}) {
  const blockers = [];
  const add = (reason) => blockers.push(reason);
  const spine = object(options.a2TrustedSpine);
  const identity = object(options.a3SharedIdentity);
  const runFixture = object(options.runFixture);
  const candidate = object(value.candidate);
  const upstream = object(value.upstream);
  const a3 = object(value.a3);
  const spineBinding = object(spine.candidate_binding);
  const expectedCore = Object.fromEntries(Object.entries(value).filter(([key]) => key !== "binding_hash"));

  if (value.schema_version !== A3_CANDIDATE_DELIVERY_BINDING_SCHEMA_VERSION) add("delivery_binding_schema_invalid");
  if (value.binding_hash !== a2CanonicalHash(expectedCore)) add("delivery_binding_hash_invalid");
  if (value.binding_state !== "exact" || array(value.blockers).length > 0) add("delivery_binding_not_exact");
  if (a3.production_ready !== false) add("production_ready_claimed_without_acceptance");
  if (a3.a2_decision_recomputed !== false) add("a2_decision_recomputed");
  if (value.safety?.a2_authority_preserved !== true) add("a2_authority_not_preserved");
  if (value.safety?.a3_release_authority_claimed !== false) add("a3_release_authority_claimed");
  if (value.safety?.human_approval_claimed !== false) add("human_approval_claimed");
  if (value.safety?.production_authority_claimed !== false) add("production_authority_claimed");
  if (value.safety?.secrets_included !== false || value.safety?.public_safe !== true) add("delivery_binding_not_public_safe");

  if (Object.keys(identity).length) {
    const identityVerification = verifyA3SharedCandidateIdentity(identity, {
      a2SourceIdentity: options.a2SourceIdentity,
      a2TrustedSpine: spine,
      runFixture,
      releaseVersion: options.releaseVersion,
      a3GitSha: options.a3GitSha
    });
    if (!identityVerification.verified) add("shared_candidate_identity_invalid");
    if (value.shared_identity_hash !== a2CanonicalHash(identity)) add("shared_identity_hash_mismatch");
    if (candidate.candidate_id !== identity.candidate_id) add("candidate_id_mismatch");
    if (a3.implementation_commit !== identity.a3?.git_sha) add("a3_implementation_commit_mismatch");
    if (a3.consumed_decision_ledger_head_hash !== identity.a3?.consumed_decision_hash) add("consumed_decision_hash_mismatch");
    if (a3.consumed_grades_hash !== identity.a3?.consumed_grades_hash) add("consumed_grades_hash_mismatch");
  }
  if (Object.keys(spine).length) {
    const authority = evaluateA2TrustedReleaseAuthority(spine);
    if (!authority.integrity_verified) add("a2_trusted_spine_invalid");
    if (candidate.candidate_id !== spineBinding.candidate_id) add("spine_candidate_id_mismatch");
    if (candidate.run_id !== spineBinding.run_id) add("spine_run_id_mismatch");
    if (candidate.release_version !== spineBinding.evidence_release_version) add("spine_release_version_mismatch");
    if (upstream.a1_source_commit !== spineBinding.a1_source_commit) add("a1_source_commit_mismatch");
    if (upstream.a1_evidence_bundle_hash !== spineBinding.a1_evidence_bundle_hash) add("a1_evidence_hash_mismatch");
    if (upstream.a2_authority_commit !== spineBinding.a2_authority_commit) add("a2_authority_commit_mismatch");
    if (upstream.a2_decision_ledger_head_hash !== spine.decision_ledger?.head_hash) add("a2_decision_hash_mismatch");
    if (upstream.a2_grades_hash !== spine.grade_results?.hash) add("a2_grades_hash_mismatch");
    if (upstream.a2_upstream_decision !== authority.upstream_decision) add("a2_upstream_decision_mismatch");
    if (upstream.a2_release_ready !== authority.release_ready) add("a2_release_ready_mismatch");
    const expectedStatus = authority.allowed ? "pending_delivery_acceptance" : "blocked_by_a2";
    if (a3.delivery_status !== expectedStatus) add("a3_delivery_status_mismatch");
  }
  if (runFixture.run_id && candidate.run_id !== runFixture.run_id) add("run_fixture_id_mismatch");
  if (options.releaseVersion && candidate.release_version !== options.releaseVersion) add("release_version_mismatch");
  if (options.a3GitSha && a3.implementation_commit !== options.a3GitSha) add("a3_git_sha_mismatch");

  const uniqueBlockers = [...new Set(blockers)].sort();
  return {
    schema_version: "a3.candidate_delivery_binding_verification.v1",
    verified: uniqueBlockers.length === 0,
    binding_state: uniqueBlockers.length === 0 ? "exact" : "invalid",
    candidate_id: candidate.candidate_id || null,
    run_id: candidate.run_id || null,
    release_version: candidate.release_version || null,
    a2_decision_ledger_head_hash: upstream.a2_decision_ledger_head_hash || null,
    a2_grades_hash: upstream.a2_grades_hash || null,
    a3_implementation_commit: a3.implementation_commit || null,
    delivery_status: a3.delivery_status || "invalid",
    production_ready: false,
    blockers: uniqueBlockers
  };
}

export function verifyA3CandidateDeliveryArtifacts(input = {}, options = {}) {
  const identityVerification = verifyA3SharedCandidateIdentity(input.a3SharedIdentity, {
    ...options,
    a2SourceIdentity: input.a2SharedIdentity,
    a2TrustedSpine: input.a2TrustedSpine,
    runFixture: input.runFixture
  });
  const deliveryVerification = verifyA3CandidateDeliveryBinding(input.candidateDeliveryBinding, {
    ...options,
    a2SourceIdentity: input.a2SharedIdentity,
    a3SharedIdentity: input.a3SharedIdentity,
    a2TrustedSpine: input.a2TrustedSpine,
    runFixture: input.runFixture
  });
  const blockers = [
    ...identityVerification.blockers.map((item) => `shared_identity:${item}`),
    ...deliveryVerification.blockers.map((item) => `delivery_binding:${item}`)
  ];
  return {
    schema_version: "a3.candidate_delivery_artifacts_verification.v1",
    verified: blockers.length === 0,
    binding_state: blockers.length === 0 ? "exact" : "invalid",
    candidate_id: deliveryVerification.candidate_id || identityVerification.candidate_id,
    run_id: deliveryVerification.run_id || identityVerification.run_id,
    release_version: deliveryVerification.release_version || identityVerification.release_version,
    a2_decision_ledger_head_hash: deliveryVerification.a2_decision_ledger_head_hash,
    a2_grades_hash: deliveryVerification.a2_grades_hash,
    a3_implementation_commit: deliveryVerification.a3_implementation_commit || identityVerification.a3_git_sha,
    delivery_status: deliveryVerification.delivery_status,
    production_ready: false,
    blockers
  };
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function array(value) {
  return Array.isArray(value) ? value : [];
}
