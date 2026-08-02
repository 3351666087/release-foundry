import { createHash } from "node:crypto";

export const A3_MULTIMODAL_PROVIDER_READINESS_INTAKE_SCHEMA_VERSION =
  "a3.a2_multimodal_provider_readiness_intake.v1";
export const A3_MULTIMODAL_PROVIDER_READINESS_SCHEMA_VERSION =
  "a3.multimodal_provider_readiness.v1";
export const A2_LOCAL_MULTIMODAL_AVAILABILITY_SCHEMA_VERSION =
  "a2.local_multimodal_availability_comparison.v1";
export const A2_OLLAMA_MULTIMODAL_LATENCY_SCHEMA_VERSION =
  "a2.ollama_multimodal_latency_probe.v1";

const ENVELOPE_FIELDS = [
  "schema_version",
  "source_commit_alias",
  "availability_comparison",
  "latency_probe",
  "release_authority",
  "public_safe",
  "raw_provider_payload_included"
];
const AVAILABILITY_FIELDS = [
  "schema_version",
  "same_case_set",
  "case_set_hash",
  "providers",
  "blockers",
  "comparison_state",
  "quality_comparison_performed",
  "provider_is_truth",
  "release_authority",
  "raw_provider_text_included",
  "public_safe"
];
const PROVIDER_FIELDS = [
  "artifact_hash",
  "attempted_count",
  "completed_count",
  "eligible_count",
  "failed_count",
  "timeout_case_count",
  "latency_seconds",
  "qualification_state"
];
const LATENCY_SUMMARY_FIELDS = ["count", "median", "p95_nearest_rank", "maximum"];
const PROBE_FIELDS = [
  "schema_version",
  "generated_at",
  "provider_id",
  "base_url_class",
  "model_id",
  "model_digest",
  "artifact_hash",
  "prompt_hash",
  "output_schema_hash",
  "unload_state",
  "timeout_seconds",
  "profiles",
  "diagnosis",
  "completed_profile_count",
  "qualification_state",
  "provider_is_truth",
  "secret_included",
  "release_authority",
  "public_safe"
];
const PROFILE_FIELDS = [
  "profile",
  "num_predict",
  "format_mode",
  "state",
  "parse_state",
  "error_class",
  "phase_receipt",
  "response_hash",
  "raw_response_included",
  "release_authority",
  "public_safe"
];
const PHASE_FIELDS = [
  "image_read_and_base64_seconds",
  "caller_wall_seconds",
  "provider_total_seconds",
  "model_load_seconds",
  "prompt_eval_seconds",
  "token_eval_seconds",
  "transport_and_client_residual_seconds"
];
const QUALIFICATION_STATES = new Set(["qualified", "blocked", "diagnostic_only", "unavailable"]);
const SECRET_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b/,
  /\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{12,}\b/,
  /\bBearer\s+[A-Za-z0-9._~-]{12,}\b/i,
  /\bCookie\s*:\s*[^\s]{12,}/i,
  /\b(?:postgres(?:ql)?|mysql):\/\/[^\s"']+/i,
  /https?:\/\/[^\s"']+/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /C:\\Users\\/i
];

export function validateA2MultimodalProviderReadinessEnvelope(value = {}) {
  const details = [];
  if (!isRecord(value)) return invalid([{ field: "provider_readiness_evidence", issue: "object_required" }]);
  exactFields(value, ENVELOPE_FIELDS, "provider_readiness_evidence", details);
  if (value.schema_version !== A3_MULTIMODAL_PROVIDER_READINESS_INTAKE_SCHEMA_VERSION) {
    details.push({ field: "schema_version", issue: "unsupported_schema_version" });
  }
  if (!/^[a-f0-9]{7,40}$/.test(String(value.source_commit_alias || ""))) {
    details.push({ field: "source_commit_alias", issue: "git_commit_alias_required" });
  }
  validateAvailabilityComparison(value.availability_comparison, details);
  validateLatencyProbe(value.latency_probe, details);
  validateEnvelopeSafety(value, details);
  validateCrossArtifactBinding(value, details);
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "provider_readiness_evidence", issue: "sensitive_or_external_material_forbidden" });
  }
  return {
    valid: details.length === 0,
    details,
    payload_hash: `sha256:${sha256(stableJson(value))}`
  };
}

export function buildA3MultimodalProviderReadiness(value = {}, options = {}) {
  const validation = validateA2MultimodalProviderReadinessEnvelope(value);
  const tenantScope = normalizeScope(options.tenantScope || options.tenant_scope || options);
  const base = {
    schema_version: A3_MULTIMODAL_PROVIDER_READINESS_SCHEMA_VERSION,
    source: options.source || "unknown",
    source_commit_alias: value.source_commit_alias || options.sourceCommitAlias || null,
    source_contracts: [
      value.availability_comparison?.schema_version || "missing",
      value.latency_probe?.schema_version || "missing"
    ],
    tenant_scope: tenantScope,
    release_authority: false,
    a2_decision_recomputed: false,
    production_ready: false
  };
  if (!validation.valid) {
    return {
      ...base,
      available: false,
      status: "invalid_upstream_contract",
      integrity: {
        status: "failed",
        finding_count: validation.details.length,
        findings: validation.details
      },
      authority_boundary: authorityBoundary(),
      safety: safetyBoundary(),
      recommendation_code: "repair_a2_multimodal_provider_readiness_contract"
    };
  }

  const availability = value.availability_comparison;
  const probe = value.latency_probe;
  const providers = Object.entries(availability.providers)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([modelId, provider]) => ({
      model_id: modelId,
      artifact_hash: provider.artifact_hash,
      qualification_state: provider.qualification_state,
      attempted_count: provider.attempted_count,
      completed_count: provider.completed_count,
      failed_count: provider.failed_count,
      timeout_case_count: provider.timeout_case_count,
      eligible_count: provider.eligible_count,
      completion_rate: ratio(provider.completed_count, provider.attempted_count),
      timeout_rate: ratio(provider.timeout_case_count, provider.attempted_count),
      eligible_rate: ratio(provider.eligible_count, provider.attempted_count),
      latency_seconds: { ...provider.latency_seconds }
    }));
  const profiles = probe.profiles.map((profile) => ({
    profile: profile.profile,
    state: profile.state,
    parse_state: profile.parse_state,
    error_class: profile.error_class,
    format_mode: profile.format_mode,
    num_predict: profile.num_predict,
    response_hash: profile.response_hash,
    phase_seconds: { ...profile.phase_receipt }
  }));
  const qualifiedProviderCount = providers.filter((provider) => provider.qualification_state === "qualified").length;
  const completedProfileCount = profiles.filter((profile) => profile.state === "completed").length;
  const validStructuredProfileCount = profiles.filter((profile) => profile.parse_state === "valid_json").length;
  const blocked = qualifiedProviderCount !== providers.length
    || providers.some((provider) => provider.eligible_count === 0)
    || completedProfileCount !== profiles.length
    || validStructuredProfileCount !== profiles.length;
  const warmWallSeconds = profiles
    .filter((profile) => profile.profile.startsWith("warm_"))
    .map((profile) => profile.phase_seconds.caller_wall_seconds)
    .filter((seconds) => typeof seconds === "number");
  const coldProfile = profiles.find((profile) => profile.profile.startsWith("cold_"));

  return {
    ...base,
    available: true,
    status: blocked ? "blocked_provider_readiness" : "diagnostic_ready_non_authoritative",
    capability_state: options.capabilityState || "peer_branch_contract_not_merged",
    integrity: {
      status: "passed",
      finding_count: 0,
      findings: [],
      a3_computed_payload_hash: validation.payload_hash
    },
    summary: {
      provider_count: providers.length,
      attempted_count: sum(providers, "attempted_count"),
      completed_count: sum(providers, "completed_count"),
      failed_count: sum(providers, "failed_count"),
      timeout_case_count: sum(providers, "timeout_case_count"),
      eligible_count: sum(providers, "eligible_count"),
      qualified_provider_count: qualifiedProviderCount,
      blocked_provider_count: providers.filter((provider) => provider.qualification_state === "blocked").length,
      profile_count: profiles.length,
      completed_profile_count: completedProfileCount,
      valid_structured_profile_count: validStructuredProfileCount,
      quality_comparison_performed: false,
      operational_health_verified: false,
      routing_ready: false,
      capacity_verified: false
    },
    availability: {
      comparison_state: availability.comparison_state,
      same_case_set: availability.same_case_set,
      case_set_hash: availability.case_set_hash,
      blockers: [...availability.blockers],
      providers
    },
    latency_diagnostic: {
      provider_id: probe.provider_id,
      model_id: probe.model_id,
      model_digest: probe.model_digest,
      artifact_hash: probe.artifact_hash,
      prompt_hash: probe.prompt_hash,
      output_schema_hash: probe.output_schema_hash,
      base_url_class: probe.base_url_class,
      generated_at: probe.generated_at,
      timeout_seconds: probe.timeout_seconds,
      unload_state: probe.unload_state,
      qualification_state: probe.qualification_state,
      diagnosis: [...probe.diagnosis],
      cold_wall_seconds: coldProfile?.phase_seconds?.caller_wall_seconds ?? null,
      fastest_warm_wall_seconds: warmWallSeconds.length ? Math.min(...warmWallSeconds) : null,
      profiles
    },
    authority_boundary: authorityBoundary(),
    safety: safetyBoundary(),
    recommendation_code: "repair_structured_output_and_provider_availability_before_qualification"
  };
}

function validateAvailabilityComparison(value, details) {
  const prefix = "availability_comparison";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, AVAILABILITY_FIELDS, prefix, details);
  if (value.schema_version !== A2_LOCAL_MULTIMODAL_AVAILABILITY_SCHEMA_VERSION) {
    details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  }
  if (typeof value.same_case_set !== "boolean") details.push({ field: `${prefix}.same_case_set`, issue: "boolean_required" });
  if (value.same_case_set === true && !isHash(value.case_set_hash)) details.push({ field: `${prefix}.case_set_hash`, issue: "sha256_required" });
  if (value.same_case_set === false && value.case_set_hash !== null && !isHash(value.case_set_hash)) {
    details.push({ field: `${prefix}.case_set_hash`, issue: "sha256_or_null_required" });
  }
  const providers = isRecord(value.providers) ? Object.entries(value.providers) : [];
  if (providers.length < 2 || providers.length > 20) {
    details.push({ field: `${prefix}.providers`, issue: "provider_count_2_to_20_required" });
  }
  providers.forEach(([modelId, provider]) => validateProviderSummary(modelId, provider, details));
  if (value.same_case_set === true && new Set(providers.map(([, provider]) => provider?.attempted_count)).size > 1) {
    details.push({ field: `${prefix}.providers`, issue: "same_case_set_attempt_count_mismatch" });
  }
  validateReasonCodes(value.blockers, `${prefix}.blockers`, details, true);
  if (!new Set(["complete", "blocked"]).has(value.comparison_state)) details.push({ field: `${prefix}.comparison_state`, issue: "unsupported_state" });
  if (value.quality_comparison_performed !== false) details.push({ field: `${prefix}.quality_comparison_performed`, issue: "must_be_false" });
  if (value.provider_is_truth !== false) details.push({ field: `${prefix}.provider_is_truth`, issue: "must_be_false" });
  if (value.release_authority !== false) details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
  if (value.raw_provider_text_included !== false) details.push({ field: `${prefix}.raw_provider_text_included`, issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
}

function validateProviderSummary(modelId, value, details) {
  const prefix = `availability_comparison.providers.${modelId}`;
  if (!safeIdentifier(modelId) || !isRecord(value)) {
    details.push({ field: prefix, issue: "safe_provider_object_required" });
    return;
  }
  exactFields(value, PROVIDER_FIELDS, prefix, details);
  if (!isHash(value.artifact_hash)) details.push({ field: `${prefix}.artifact_hash`, issue: "sha256_required" });
  for (const field of ["attempted_count", "completed_count", "eligible_count", "failed_count", "timeout_case_count"]) {
    if (!nonNegativeInteger(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
  }
  if (nonNegativeInteger(value.attempted_count) && value.completed_count + value.failed_count !== value.attempted_count) {
    details.push({ field: prefix, issue: "attempted_count_conservation_failed" });
  }
  if (value.eligible_count > value.completed_count) details.push({ field: `${prefix}.eligible_count`, issue: "eligible_exceeds_completed" });
  if (value.timeout_case_count > value.failed_count) details.push({ field: `${prefix}.timeout_case_count`, issue: "timeout_exceeds_failed" });
  validateLatencySummary(value.latency_seconds, value.attempted_count, `${prefix}.latency_seconds`, details);
  if (!QUALIFICATION_STATES.has(value.qualification_state)) details.push({ field: `${prefix}.qualification_state`, issue: "unsupported_state" });
}

function validateLatencySummary(value, attemptedCount, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, LATENCY_SUMMARY_FIELDS, prefix, details);
  if (!nonNegativeInteger(value.count) || value.count !== attemptedCount) details.push({ field: `${prefix}.count`, issue: "attempted_count_mismatch" });
  for (const field of ["median", "p95_nearest_rank", "maximum"]) {
    if (value[field] !== null && !nonNegativeNumber(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_number_or_null_required" });
  }
  const ordered = [value.median, value.p95_nearest_rank, value.maximum];
  if (ordered.every((item) => typeof item === "number") && !(ordered[0] <= ordered[1] && ordered[1] <= ordered[2])) {
    details.push({ field: prefix, issue: "latency_order_invalid" });
  }
}

function validateLatencyProbe(value, details) {
  const prefix = "latency_probe";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, PROBE_FIELDS, prefix, details);
  if (value.schema_version !== A2_OLLAMA_MULTIMODAL_LATENCY_SCHEMA_VERSION) details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  if (!validIsoDate(value.generated_at)) details.push({ field: `${prefix}.generated_at`, issue: "iso_datetime_required" });
  if (value.provider_id !== "ollama-local") details.push({ field: `${prefix}.provider_id`, issue: "ollama_local_required" });
  if (value.base_url_class !== "loopback") details.push({ field: `${prefix}.base_url_class`, issue: "loopback_required" });
  if (!safeIdentifier(value.model_id)) details.push({ field: `${prefix}.model_id`, issue: "safe_identifier_required" });
  for (const field of ["model_digest", "artifact_hash", "prompt_hash", "output_schema_hash"]) {
    if (!isHash(value[field])) details.push({ field: `${prefix}.${field}`, issue: "sha256_required" });
  }
  if (!new Set(["requested", "unconfirmed"]).has(value.unload_state)) details.push({ field: `${prefix}.unload_state`, issue: "unsupported_state" });
  if (!positiveNumber(value.timeout_seconds)) details.push({ field: `${prefix}.timeout_seconds`, issue: "positive_number_required" });
  if (!Array.isArray(value.profiles) || value.profiles.length !== 4) {
    details.push({ field: `${prefix}.profiles`, issue: "exactly_four_profiles_required" });
  } else {
    value.profiles.forEach((profile, index) => validateProfile(profile, `${prefix}.profiles[${index}]`, details));
    if (new Set(value.profiles.map((profile) => profile?.profile)).size !== value.profiles.length) {
      details.push({ field: `${prefix}.profiles`, issue: "unique_profile_names_required" });
    }
  }
  validateReasonCodes(value.diagnosis, `${prefix}.diagnosis`, details, false);
  const completed = Array.isArray(value.profiles) ? value.profiles.filter((profile) => profile?.state === "completed").length : 0;
  if (!nonNegativeInteger(value.completed_profile_count) || value.completed_profile_count !== completed) {
    details.push({ field: `${prefix}.completed_profile_count`, issue: "derived_count_mismatch" });
  }
  if (!new Set(["diagnostic_only", "blocked"]).has(value.qualification_state)) details.push({ field: `${prefix}.qualification_state`, issue: "unsupported_state" });
  if (value.provider_is_truth !== false) details.push({ field: `${prefix}.provider_is_truth`, issue: "must_be_false" });
  if (value.secret_included !== false) details.push({ field: `${prefix}.secret_included`, issue: "must_be_false" });
  if (value.release_authority !== false) details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
}

function validateProfile(value, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, PROFILE_FIELDS, prefix, details);
  if (!safeIdentifier(value.profile)) details.push({ field: `${prefix}.profile`, issue: "safe_identifier_required" });
  if (!Number.isInteger(value.num_predict) || value.num_predict < 1 || value.num_predict > 4096) details.push({ field: `${prefix}.num_predict`, issue: "integer_1_to_4096_required" });
  if (!new Set(["plain", "json_schema"]).has(value.format_mode)) details.push({ field: `${prefix}.format_mode`, issue: "unsupported_mode" });
  if (!new Set(["completed", "failed"]).has(value.state)) details.push({ field: `${prefix}.state`, issue: "unsupported_state" });
  if (!new Set(["valid_json", "invalid_structured_output", "unavailable"]).has(value.parse_state)) details.push({ field: `${prefix}.parse_state`, issue: "unsupported_state" });
  if (!safeIdentifier(value.error_class, true)) details.push({ field: `${prefix}.error_class`, issue: "safe_reason_code_required" });
  if (value.state === "completed" && value.parse_state !== "valid_json") details.push({ field: prefix, issue: "completed_profile_requires_valid_json" });
  if (value.state === "failed" && value.parse_state === "valid_json") details.push({ field: prefix, issue: "failed_profile_cannot_be_valid_json" });
  validatePhaseReceipt(value.phase_receipt, `${prefix}.phase_receipt`, details);
  if (value.response_hash !== null && !isHash(value.response_hash)) details.push({ field: `${prefix}.response_hash`, issue: "sha256_or_null_required" });
  if (value.raw_response_included !== false) details.push({ field: `${prefix}.raw_response_included`, issue: "must_be_false" });
  if (value.release_authority !== false) details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
}

function validatePhaseReceipt(value, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, PHASE_FIELDS, prefix, details);
  for (const field of PHASE_FIELDS) {
    if (!nonNegativeNumber(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_number_required" });
  }
  if (PHASE_FIELDS.every((field) => nonNegativeNumber(value[field]))) {
    const observedResidual = value.caller_wall_seconds - value.provider_total_seconds;
    if (!closeNumber(observedResidual, value.transport_and_client_residual_seconds, 0.001)) {
      details.push({ field: prefix, issue: "caller_provider_residual_mismatch" });
    }
  }
}

function validateEnvelopeSafety(value, details) {
  if (value.release_authority !== false) details.push({ field: "release_authority", issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: "public_safe", issue: "must_be_true" });
  if (value.raw_provider_payload_included !== false) details.push({ field: "raw_provider_payload_included", issue: "must_be_false" });
}

function validateCrossArtifactBinding(value, details) {
  const modelId = value.latency_probe?.model_id;
  if (safeIdentifier(modelId) && isRecord(value.availability_comparison?.providers)
    && !Object.hasOwn(value.availability_comparison.providers, modelId)) {
    details.push({ field: "latency_probe.model_id", issue: "model_missing_from_availability_comparison" });
  }
}

function exactFields(value, allowed, prefix, details) {
  if (!isRecord(value)) return;
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) details.push({ field: `${prefix}.${key}`, issue: "unknown_field" });
  }
  for (const key of allowed) {
    if (!Object.hasOwn(value, key)) details.push({ field: `${prefix}.${key}`, issue: "required_field_missing" });
  }
}

function validateReasonCodes(value, prefix, details, allowEmpty) {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0) || value.length > 50) {
    details.push({ field: prefix, issue: allowEmpty ? "reason_code_array_required" : "non_empty_reason_code_array_required" });
    return;
  }
  value.forEach((item, index) => {
    if (!safeIdentifier(item)) details.push({ field: `${prefix}[${index}]`, issue: "safe_reason_code_required" });
  });
  if (new Set(value).size !== value.length) details.push({ field: prefix, issue: "unique_values_required" });
}

function authorityBoundary() {
  return {
    provider_is_truth: false,
    quality_comparison_performed: false,
    operational_health_verified: false,
    routing_or_capacity_authority: "A1",
    evaluation_and_qualification_authority: "A2",
    display_and_workflow_owner: "A3",
    release_authority: false,
    a2_decision_recomputed: false,
    release_decision_changed: false,
    production_ready: false
  };
}

function safetyBoundary() {
  return {
    public_safe: true,
    raw_provider_payload_included: false,
    secret_included: false,
    endpoint_url_included: false,
    model_binary_included: false,
    private_media_included: false,
    hash_and_aggregate_metadata_only: true
  };
}

function normalizeScope(value = {}) {
  return {
    organization_id: value.organization_id || value.organizationId || "org-local",
    tenant_id: value.tenant_id || value.tenantId || "tenant-local",
    workspace_id: value.workspace_id || value.workspaceId || "workspace-local",
    project_id: value.project_id || value.projectId || "project-local",
    environment_id: value.environment_id || value.environmentId || "staging"
  };
}

function invalid(details) {
  return { valid: false, details, payload_hash: null };
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isHash(value) {
  return /^sha256:[a-f0-9]{64}$/.test(String(value || ""));
}

function safeIdentifier(value, allowEmpty = false) {
  if (allowEmpty && value === "") return true;
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(String(value || ""));
}

function validIsoDate(value) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) && value.includes("T");
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function nonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function positiveNumber(value) {
  return nonNegativeNumber(value) && value > 0;
}

function closeNumber(left, right, tolerance = 1e-9) {
  return typeof left === "number" && typeof right === "number" && Math.abs(left - right) <= tolerance;
}

function ratio(numerator, denominator) {
  return denominator > 0 ? numerator / denominator : null;
}

function sum(items, field) {
  return items.reduce((total, item) => total + (Number(item[field]) || 0), 0);
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (!isRecord(value)) return JSON.stringify(value);
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
}
