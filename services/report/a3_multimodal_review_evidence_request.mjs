import { createHash } from "node:crypto";

export const A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_EVENT_SCHEMA_VERSION =
  "a3.multimodal_review_evidence_request_event.v1";
export const A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_SCHEMA_VERSION =
  "a3.multimodal_review_evidence_request.v1";
export const A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_RECEIPT_SCHEMA_VERSION =
  "a3.multimodal_review_evidence_request_receipt.v1";

export const A3_MULTIMODAL_REVIEW_EVIDENCE_KINDS = Object.freeze([
  "a1_run_trace",
  "a1_tool_call",
  "a1_artifact",
  "a2_judge_receipt",
  "a2_review_receipt",
  "media_evidence",
  "provider_identity",
  "candidate_binding"
]);

export const A3_MULTIMODAL_REVIEW_EVIDENCE_OWNER_LANES = Object.freeze([
  "execution",
  "evaluation",
  "customer_operator"
]);

const EVIDENCE_KIND_SET = new Set(A3_MULTIMODAL_REVIEW_EVIDENCE_KINDS);
const OWNER_LANE_SET = new Set(A3_MULTIMODAL_REVIEW_EVIDENCE_OWNER_LANES);
const EVENT_TYPES = new Set(["requested", "submitted", "accepted", "rejected", "cancelled"]);
const REVIEW_ACTIONS = new Set(["accept", "reject", "cancel"]);
const CREATE_FIELDS = new Set([
  "expected_version",
  "owner_lane",
  "required_evidence_kinds",
  "due_at",
  "reason_code"
]);
const SUBMISSION_FIELDS = new Set([
  "expected_version",
  "owner_lane",
  "evidence_refs",
  "reason_code"
]);
const REVIEW_FIELDS = new Set([
  "expected_version",
  "action",
  "reason_code"
]);
const MAX_DUE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

export function buildA3MultimodalReviewEvidenceRequestProjection(queue = {}, events = [], options = {}) {
  const now = normalizedDate(options.now);
  const queueItems = Array.isArray(queue.items) ? queue.items : [];
  const knownQueueIds = new Set(queueItems.map((item) => item.queue_id));
  const validEvents = [];
  let invalidEventCount = 0;

  for (const event of Array.isArray(events) ? events : []) {
    if (validEvidenceRequestEvent(event) && knownQueueIds.has(event.queue_id)) {
      validEvents.push(event);
    } else {
      invalidEventCount += 1;
    }
  }

  const byQueue = groupBy(validEvents, "queue_id");
  const items = queueItems.map((item) => {
    const queueEvents = byQueue.get(item.queue_id) || [];
    const requests = buildRequestStates(queueEvents, now);
    return {
      ...item,
      evidence_request_summary: summarizeRequests(requests),
      evidence_requests: requests
    };
  });
  const requests = items.flatMap((item) => item.evidence_requests);
  const summary = summarizeRequests(requests);

  return {
    ...queue,
    summary: {
      ...(queue.summary || {}),
      evidence_request_count: summary.total_count,
      evidence_request_open_count: summary.open_count,
      evidence_request_overdue_count: summary.overdue_count,
      evidence_request_submitted_count: summary.submitted_count,
      evidence_request_accepted_count: summary.accepted_count,
      evidence_request_cancelled_count: summary.cancelled_count,
      evidence_request_event_count: validEvents.length,
      evidence_request_invalid_event_count: invalidEventCount
    },
    evidence_request_workflow: {
      schema_version: "a3.multimodal_review_evidence_request_index.v1",
      mode: "append_only_hash_references",
      statuses: ["open", "overdue", "submitted", "accepted", "cancelled"],
      owner_lanes: A3_MULTIMODAL_REVIEW_EVIDENCE_OWNER_LANES,
      evidence_kinds: A3_MULTIMODAL_REVIEW_EVIDENCE_KINDS,
      optimistic_concurrency: "expected_version",
      idempotency: "header_only",
      raw_evidence_allowed: false,
      release_authority: false,
      authoritative_human_disposition_recorded: false,
      a2_decision_recomputed: false
    },
    authority_boundary: {
      ...(queue.authority_boundary || {}),
      evidence_request_acceptance_is_human_disposition: false,
      evidence_requests_release_authority: false,
      evidence_requests_change_a2_decision: false
    },
    items,
    safety: {
      ...(queue.safety || {}),
      evidence_request_hash_references_only: true,
      raw_evidence_exposed: false,
      signed_url_exposed: false,
      free_text_evidence_exposed: false
    }
  };
}

export function planA3MultimodalReviewEvidenceRequestTransition(queue = {}, events = [], input = {}, context = {}) {
  const operation = String(context.operation || "");
  const details = validateTransitionInput(operation, input, context);
  const queueItem = (Array.isArray(queue.items) ? queue.items : [])
    .find((item) => item.queue_id === context.queueId);
  if (!queueItem) {
    return failure("queue_item_not_found", 404, [{ field: "queue_id", issue: "not_found" }]);
  }
  if (details.length) {
    return failure(`invalid_evidence_request_${operation || "action"}`, 400, details);
  }

  const now = normalizedDate(context.now);
  const queueEvents = (Array.isArray(events) ? events : [])
    .filter((event) => validEvidenceRequestEvent(event) && event.queue_id === context.queueId);
  const requests = buildRequestStates(queueEvents, now);
  const current = context.requestId
    ? requests.find((request) => request.request_id === context.requestId)
    : null;

  if (operation !== "create" && !current) {
    return failure("evidence_request_not_found", 404, [{ field: "request_id", issue: "not_found" }]);
  }
  const currentVersion = current?.version || 0;
  if (input.expected_version !== currentVersion) {
    return failure("evidence_request_version_conflict", 409, [{
      field: "expected_version",
      issue: "stale_version",
      expected: currentVersion
    }]);
  }
  if (current?.integrity?.status === "failed") {
    return failure("evidence_request_integrity_invalid", 409, [{ field: "request_id", issue: "event_chain_invalid" }]);
  }

  if (["create", "review"].includes(operation)) {
    const leaseFailure = activeLeaseFailure(queueItem, context.actorHash);
    if (leaseFailure) return leaseFailure;
  }

  if (operation === "create") {
    const dueAt = new Date(input.due_at);
    if (dueAt.getTime() <= now.getTime() || dueAt.getTime() - now.getTime() > MAX_DUE_WINDOW_MS) {
      return failure("invalid_evidence_request_create", 400, [{
        field: "due_at",
        issue: "future_time_within_30_days_required"
      }]);
    }
    const createdAt = now.toISOString();
    const requestId = evidenceRequestId({
      source: context.source,
      tenantScope: context.tenantScope,
      queueItem,
      ownerLane: input.owner_lane,
      requiredEvidenceKinds: normalizedKinds(input.required_evidence_kinds),
      dueAt: dueAt.toISOString(),
      reasonCode: input.reason_code,
      createdAt
    });
    const event = createEvent({
      source: context.source,
      tenantScope: context.tenantScope,
      queueItem,
      requestId,
      eventType: "requested",
      version: 1,
      actorHash: context.actorHash,
      actorRole: context.actorRole,
      ownerLane: input.owner_lane,
      requiredEvidenceKinds: normalizedKinds(input.required_evidence_kinds),
      evidenceRefs: [],
      dueAt: dueAt.toISOString(),
      reasonCode: input.reason_code,
      previousEventHash: null,
      createdAt
    });
    return success(event, requestState([event], now));
  }

  if (operation === "submit") {
    if (!["open", "overdue"].includes(current.status)) {
      return failure("evidence_request_not_open", 409, [{ field: "request_id", issue: "open_or_overdue_required" }]);
    }
    if (input.owner_lane !== current.owner_lane) {
      return failure("evidence_request_owner_lane_mismatch", 409, [{ field: "owner_lane", issue: "must_match_request" }]);
    }
    const evidenceRefs = normalizedEvidenceRefs(input.evidence_refs);
    const submittedKinds = new Set(evidenceRefs.map((item) => item.kind));
    const missingKinds = current.required_evidence_kinds.filter((kind) => !submittedKinds.has(kind));
    const unexpectedKinds = [...submittedKinds].filter((kind) => !current.required_evidence_kinds.includes(kind));
    if (missingKinds.length) {
      return failure("evidence_request_incomplete_submission", 409, missingKinds.map((kind) => ({
        field: "evidence_refs",
        issue: "required_kind_missing",
        kind
      })));
    }
    if (unexpectedKinds.length) {
      return failure("evidence_request_unrequested_evidence", 409, unexpectedKinds.map((kind) => ({
        field: "evidence_refs",
        issue: "evidence_kind_not_requested",
        kind
      })));
    }
    const event = createEvent({
      source: context.source,
      tenantScope: context.tenantScope,
      queueItem,
      requestId: current.request_id,
      eventType: "submitted",
      version: current.version + 1,
      actorHash: context.actorHash,
      actorRole: context.actorRole,
      ownerLane: current.owner_lane,
      requiredEvidenceKinds: current.required_evidence_kinds,
      evidenceRefs,
      dueAt: current.due_at,
      reasonCode: input.reason_code,
      previousEventHash: current.terminal_event_hash,
      createdAt: now.toISOString()
    });
    return success(event, requestState([...current.history, event], now));
  }

  if (operation === "review") {
    if (["accept", "reject"].includes(input.action) && current.status !== "submitted") {
      return failure("evidence_request_not_submitted", 409, [{ field: "request_id", issue: "submitted_required" }]);
    }
    if (input.action === "cancel" && !["open", "overdue", "submitted"].includes(current.status)) {
      return failure("evidence_request_not_cancellable", 409, [{ field: "request_id", issue: "active_request_required" }]);
    }
    const eventType = { accept: "accepted", reject: "rejected", cancel: "cancelled" }[input.action];
    const event = createEvent({
      source: context.source,
      tenantScope: context.tenantScope,
      queueItem,
      requestId: current.request_id,
      eventType,
      version: current.version + 1,
      actorHash: context.actorHash,
      actorRole: context.actorRole,
      ownerLane: current.owner_lane,
      requiredEvidenceKinds: current.required_evidence_kinds,
      evidenceRefs: [],
      dueAt: current.due_at,
      reasonCode: input.reason_code,
      previousEventHash: current.terminal_event_hash,
      createdAt: now.toISOString()
    });
    return success(event, requestState([...current.history, event], now));
  }

  return failure("unsupported_evidence_request_operation", 400, [{ field: "operation", issue: "unsupported" }]);
}

function validateTransitionInput(operation, input, context) {
  const details = [];
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return [{ field: operation || "evidence_request", issue: "object_required" }];
  }
  const fields = operation === "create"
    ? CREATE_FIELDS
    : operation === "submit"
      ? SUBMISSION_FIELDS
      : operation === "review"
        ? REVIEW_FIELDS
        : new Set();
  for (const field of Object.keys(input)) {
    if (!fields.has(field)) details.push({ field, issue: "unexpected_field" });
  }
  if (!["create", "submit", "review"].includes(operation)) {
    details.push({ field: "operation", issue: "unsupported" });
  }
  if (!Number.isInteger(input.expected_version) || input.expected_version < 0) {
    details.push({ field: "expected_version", issue: "non_negative_integer_required" });
  }
  if (!safeIdentityHash(context.actorHash)) {
    details.push({ field: "actor_hash", issue: "server_verified_hash_required" });
  }
  if (!safeRole(context.actorRole)) {
    details.push({ field: "actor_role", issue: "server_verified_role_required" });
  }
  if (operation === "create") {
    if (input.expected_version !== 0) details.push({ field: "expected_version", issue: "zero_required_for_create" });
    if (!OWNER_LANE_SET.has(input.owner_lane)) details.push({ field: "owner_lane", issue: "unsupported_owner_lane" });
    details.push(...validateEvidenceKinds(input.required_evidence_kinds));
    if (!validIsoTimestamp(input.due_at)) details.push({ field: "due_at", issue: "iso_timestamp_required" });
  }
  if (operation === "submit") {
    if (!OWNER_LANE_SET.has(input.owner_lane)) details.push({ field: "owner_lane", issue: "unsupported_owner_lane" });
    details.push(...validateEvidenceRefs(input.evidence_refs));
  }
  if (operation === "review" && !REVIEW_ACTIONS.has(input.action)) {
    details.push({ field: "action", issue: "accept_reject_or_cancel_required" });
  }
  if (!validReasonCode(input.reason_code)) {
    details.push({ field: "reason_code", issue: "lower_snake_case_required" });
  }
  return details;
}

function activeLeaseFailure(queueItem, actorHash) {
  const assignment = queueItem.operational_state || {};
  if (assignment.status !== "claimed") {
    return failure("evidence_request_active_assignment_required", 409, [{
      field: "queue_id",
      issue: "active_assignment_lease_required"
    }]);
  }
  if (assignment.assigned_reviewer_hash !== actorHash) {
    return failure("evidence_request_assignment_not_owned", 403, [{
      field: "actor_hash",
      issue: "active_assignment_owner_required"
    }]);
  }
  return null;
}

function createEvent(input) {
  const scope = normalizeScope(input.tenantScope);
  const body = {
    schema_version: A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_EVENT_SCHEMA_VERSION,
    source: input.source || "unknown",
    ...scope,
    tenant_scope: scope,
    queue_id: input.queueItem.queue_id,
    case_id: input.queueItem.case_id,
    comparison_hash: input.queueItem.comparison_hash,
    request_id: input.requestId,
    event_type: input.eventType,
    version: input.version,
    actor_hash: input.actorHash,
    actor_role: input.actorRole,
    owner_lane: input.ownerLane,
    required_evidence_kinds: normalizedKinds(input.requiredEvidenceKinds),
    evidence_refs: normalizedEvidenceRefs(input.evidenceRefs),
    due_at: input.dueAt,
    reason_code: input.reasonCode,
    previous_event_hash: input.previousEventHash || null,
    created_at: input.createdAt,
    release_authority: false,
    authoritative_human_disposition_recorded: false,
    a2_decision_recomputed: false,
    safety: evidenceRequestSafety()
  };
  const digest = sha256(stableJson(body));
  return {
    ...body,
    event_id: `mmre_${digest.slice(0, 20)}`,
    event_hash: `sha256:${digest}`
  };
}

function buildRequestStates(events, now) {
  const byRequest = groupBy(events, "request_id");
  return [...byRequest.values()]
    .map((history) => requestState(history, now))
    .sort((left, right) => String(left.created_at).localeCompare(String(right.created_at)));
}

function requestState(events, now) {
  const sorted = [...events].sort(eventOrder);
  const first = sorted[0];
  const latest = sorted.at(-1);
  const integrityFindings = validateEventChain(sorted);
  let status = "open";
  if (latest?.event_type === "submitted") status = "submitted";
  if (latest?.event_type === "accepted") status = "accepted";
  if (latest?.event_type === "cancelled") status = "cancelled";
  if (["requested", "rejected"].includes(latest?.event_type)
    && new Date(latest.due_at).getTime() <= now.getTime()) status = "overdue";
  const submission = [...sorted].reverse().find((event) => event.event_type === "submitted");
  const sanitizedHistory = sorted.map(sanitizeEvent);
  return {
    schema_version: A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_SCHEMA_VERSION,
    request_id: first?.request_id || "unknown",
    queue_id: first?.queue_id || "unknown",
    case_id: first?.case_id || "unknown",
    comparison_hash: first?.comparison_hash || null,
    status,
    version: latest?.version || 0,
    owner_lane: first?.owner_lane || "unknown",
    required_evidence_kinds: normalizedKinds(first?.required_evidence_kinds),
    submitted_evidence_kinds: normalizedKinds((submission?.evidence_refs || []).map((item) => item.kind)),
    evidence_refs: normalizedEvidenceRefs(submission?.evidence_refs || []),
    due_at: first?.due_at || null,
    overdue: status === "overdue",
    last_action: latest?.event_type || null,
    last_action_at: latest?.created_at || null,
    last_reason_code: latest?.reason_code || null,
    created_at: first?.created_at || null,
    event_count: sorted.length,
    terminal_event_hash: latest?.event_hash || null,
    history: sanitizedHistory,
    integrity: {
      status: integrityFindings.length ? "failed" : "passed",
      finding_count: integrityFindings.length,
      findings: integrityFindings
    },
    authority_boundary: {
      evidence_accepted: status === "accepted",
      authoritative_human_disposition_recorded: false,
      release_authority: false,
      a2_decision_recomputed: false,
      release_decision_changed: false
    },
    safety: evidenceRequestSafety()
  };
}

function summarizeRequests(requests = []) {
  const values = Array.isArray(requests) ? requests : [];
  return {
    schema_version: "a3.multimodal_review_evidence_request_summary.v1",
    total_count: values.length,
    open_count: values.filter((item) => item.status === "open").length,
    overdue_count: values.filter((item) => item.status === "overdue").length,
    submitted_count: values.filter((item) => item.status === "submitted").length,
    accepted_count: values.filter((item) => item.status === "accepted").length,
    cancelled_count: values.filter((item) => item.status === "cancelled").length,
    integrity_failed_count: values.filter((item) => item.integrity?.status === "failed").length
  };
}

function validateEventChain(events) {
  const findings = [];
  const first = events[0];
  let previousHash = null;
  let previousCreatedAt = null;
  let lifecycleState = "none";
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (event.version !== index + 1) findings.push(finding("event_version_gap", index));
    if ((event.previous_event_hash || null) !== previousHash) findings.push(finding("previous_event_hash_mismatch", index));
    if (index === 0 && event.event_type !== "requested") findings.push(finding("first_event_not_requested", index));
    if (index > 0 && !sameRequestSubject(event, first)) findings.push(finding("request_subject_mismatch", index));
    if (previousCreatedAt && new Date(event.created_at).getTime() < new Date(previousCreatedAt).getTime()) {
      findings.push(finding("event_time_reordered", index));
    }
    const transition = evidenceRequestLifecycleTransition(lifecycleState, event.event_type);
    if (!transition.valid) findings.push(finding("invalid_lifecycle_transition", index));
    else lifecycleState = transition.next;
    previousHash = event.event_hash;
    previousCreatedAt = event.created_at;
  }
  if (first) {
    const expectedRequestId = evidenceRequestId({
      source: first.source,
      tenantScope: first,
      queueItem: first,
      ownerLane: first.owner_lane,
      requiredEvidenceKinds: first.required_evidence_kinds,
      dueAt: first.due_at,
      reasonCode: first.reason_code,
      createdAt: first.created_at
    });
    if (first.request_id !== expectedRequestId) findings.push(finding("request_id_binding_mismatch", 0));
  }
  return findings;
}

function evidenceRequestLifecycleTransition(current, eventType) {
  if (current === "none" && eventType === "requested") return { valid: true, next: "open" };
  if (current === "open" && eventType === "submitted") return { valid: true, next: "submitted" };
  if (current === "submitted" && eventType === "accepted") return { valid: true, next: "terminal" };
  if (current === "submitted" && eventType === "rejected") return { valid: true, next: "open" };
  if (["open", "submitted"].includes(current) && eventType === "cancelled") return { valid: true, next: "terminal" };
  return { valid: false, next: current };
}

function sameRequestSubject(event, first) {
  return [
    "source",
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
    "queue_id",
    "case_id",
    "comparison_hash",
    "request_id",
    "owner_lane",
    "due_at"
  ].every((field) => event[field] === first[field])
    && stableJson(normalizedKinds(event.required_evidence_kinds)) === stableJson(normalizedKinds(first.required_evidence_kinds));
}

function validEvidenceRequestEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) return false;
  const body = canonicalEventBody(event);
  const digest = sha256(stableJson(body));
  const allowedFields = new Set([...Object.keys(body), "event_id", "event_hash"]);
  return Object.keys(event).every((field) => allowedFields.has(field))
    && event.schema_version === A3_MULTIMODAL_REVIEW_EVIDENCE_REQUEST_EVENT_SCHEMA_VERSION
    && EVENT_TYPES.has(event.event_type)
    && safeSource(event.source)
    && safeSubjectId(event.queue_id)
    && safeSubjectId(event.case_id)
    && safeSha256(event.comparison_hash)
    && /^mmreq_[a-f0-9]{20}$/.test(String(event.request_id || ""))
    && Number.isInteger(event.version)
    && event.version > 0
    && safeIdentityHash(event.actor_hash)
    && safeRole(event.actor_role)
    && OWNER_LANE_SET.has(event.owner_lane)
    && validateEvidenceKinds(event.required_evidence_kinds).length === 0
    && (event.event_type === "submitted"
      ? validateEvidenceRefs(event.evidence_refs).length === 0
      : Array.isArray(event.evidence_refs) && event.evidence_refs.length === 0)
    && validIsoTimestamp(event.due_at)
    && validIsoTimestamp(event.created_at)
    && validReasonCode(event.reason_code)
    && exactScopeIsPresent(event)
    && event.release_authority === false
    && event.authoritative_human_disposition_recorded === false
    && event.a2_decision_recomputed === false
    && event.event_id === `mmre_${digest.slice(0, 20)}`
    && event.event_hash === `sha256:${digest}`
    && evidenceRequestSafetyIsValid(event.safety)
    && safePacketText(JSON.stringify(body));
}

function canonicalEventBody(event = {}) {
  const scope = normalizeScope(event);
  return {
    schema_version: event.schema_version,
    source: event.source,
    ...scope,
    tenant_scope: scope,
    queue_id: event.queue_id,
    case_id: event.case_id,
    comparison_hash: event.comparison_hash,
    request_id: event.request_id,
    event_type: event.event_type,
    version: event.version,
    actor_hash: event.actor_hash,
    actor_role: event.actor_role,
    owner_lane: event.owner_lane,
    required_evidence_kinds: normalizedKinds(event.required_evidence_kinds),
    evidence_refs: normalizedEvidenceRefs(event.evidence_refs),
    due_at: event.due_at,
    reason_code: event.reason_code,
    previous_event_hash: event.previous_event_hash || null,
    created_at: event.created_at,
    release_authority: false,
    authoritative_human_disposition_recorded: false,
    a2_decision_recomputed: false,
    safety: evidenceRequestSafety()
  };
}

function sanitizeEvent(event) {
  return {
    ...canonicalEventBody(event),
    event_id: event.event_id,
    event_hash: event.event_hash
  };
}

function evidenceRequestId(input) {
  const scope = normalizeScope(input.tenantScope);
  return `mmreq_${sha256(stableJson({
    source: input.source || "unknown",
    ...scope,
    queue_id: input.queueItem.queue_id,
    case_id: input.queueItem.case_id,
    comparison_hash: input.queueItem.comparison_hash,
    owner_lane: input.ownerLane,
    required_evidence_kinds: input.requiredEvidenceKinds,
    due_at: input.dueAt,
    reason_code: input.reasonCode,
    created_at: input.createdAt
  })).slice(0, 20)}`;
}

function validateEvidenceKinds(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 8) {
    return [{ field: "required_evidence_kinds", issue: "array_1_to_8_required" }];
  }
  const details = [];
  const seen = new Set();
  for (const [index, kind] of value.entries()) {
    if (!EVIDENCE_KIND_SET.has(kind)) details.push({ field: `required_evidence_kinds[${index}]`, issue: "unsupported_evidence_kind" });
    if (seen.has(kind)) details.push({ field: `required_evidence_kinds[${index}]`, issue: "duplicate_evidence_kind" });
    seen.add(kind);
  }
  return details;
}

function validateEvidenceRefs(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 24) {
    return [{ field: "evidence_refs", issue: "array_1_to_24_required" }];
  }
  const details = [];
  const fingerprints = new Set();
  for (const [index, item] of value.entries()) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      details.push({ field: `evidence_refs[${index}]`, issue: "object_required" });
      continue;
    }
    for (const field of Object.keys(item)) {
      if (!["kind", "evidence_hash", "binding_hash"].includes(field)) {
        details.push({ field: `evidence_refs[${index}].${field}`, issue: "unexpected_field" });
      }
    }
    if (!EVIDENCE_KIND_SET.has(item.kind)) details.push({ field: `evidence_refs[${index}].kind`, issue: "unsupported_evidence_kind" });
    if (!safeSha256(item.evidence_hash)) details.push({ field: `evidence_refs[${index}].evidence_hash`, issue: "sha256_required" });
    if (item.binding_hash !== undefined && !safeSha256(item.binding_hash)) {
      details.push({ field: `evidence_refs[${index}].binding_hash`, issue: "sha256_required" });
    }
    const fingerprint = `${item.kind}:${String(item.evidence_hash).toLowerCase()}`;
    if (fingerprints.has(fingerprint)) details.push({ field: `evidence_refs[${index}]`, issue: "duplicate_reference" });
    fingerprints.add(fingerprint);
  }
  return details;
}

function normalizedEvidenceRefs(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => ({
      kind: item?.kind,
      evidence_hash: typeof item?.evidence_hash === "string" ? item.evidence_hash.toLowerCase() : item?.evidence_hash,
      ...(item?.binding_hash ? { binding_hash: String(item.binding_hash).toLowerCase() } : {})
    }))
    .sort((left, right) => `${left.kind}:${left.evidence_hash}`.localeCompare(`${right.kind}:${right.evidence_hash}`));
}

function normalizedKinds(value) {
  return [...new Set(Array.isArray(value) ? value : [])].sort();
}

function evidenceRequestSafety() {
  return {
    hash_references_only: true,
    raw_evidence_included: false,
    raw_model_payload_included: false,
    raw_identity_included: false,
    signed_url_included: false,
    secret_values_included: false,
    free_text_included: false
  };
}

function evidenceRequestSafetyIsValid(value = {}) {
  return value.hash_references_only === true
    && value.raw_evidence_included === false
    && value.raw_model_payload_included === false
    && value.raw_identity_included === false
    && value.signed_url_included === false
    && value.secret_values_included === false
    && value.free_text_included === false;
}

function success(event, evidenceRequest) {
  return {
    valid: true,
    statusCode: event.event_type === "requested" ? 201 : 200,
    event,
    evidence_request: evidenceRequest
  };
}

function failure(error, statusCode, details) {
  return { valid: false, error, statusCode, details };
}

function finding(id, index) {
  return { id, severity: "blocking", event_position: index + 1 };
}

function groupBy(values, field) {
  const grouped = new Map();
  for (const value of values) {
    const key = value[field];
    const items = grouped.get(key) || [];
    items.push(value);
    grouped.set(key, items);
  }
  return grouped;
}

function eventOrder(left, right) {
  return Number(left.version) - Number(right.version)
    || String(left.created_at).localeCompare(String(right.created_at));
}

function safeIdentityHash(value) {
  const text = String(value || "");
  return /^[A-Za-z0-9:_-]{8,160}$/.test(text)
    && !/bearer|cookie|secret|token|password|@|https?:/i.test(text);
}

function safeRole(value) {
  return ["owner", "admin", "developer", "reviewer", "service_account"].includes(String(value || ""));
}

function safeSha256(value) {
  return /^sha256:[a-f0-9]{64}$/i.test(String(value || ""));
}

function safeSource(value) {
  return /^[A-Za-z0-9._-]{1,160}$/.test(String(value || ""));
}

function safeSubjectId(value) {
  const text = String(value || "");
  return text.length >= 1
    && text.length <= 240
    && !/Bearer|Cookie|secret|token|password|@|https?:|[\\/]/i.test(text);
}

function exactScopeIsPresent(value = {}) {
  return ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"].every((field) => (
    typeof value[field] === "string"
    && value[field].length > 0
    && value.tenant_scope?.[field] === value[field]
  ));
}

function validReasonCode(value) {
  return /^[a-z0-9_]{3,64}$/.test(String(value || ""));
}

function validIsoTimestamp(value) {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)
    && !Number.isNaN(new Date(value).getTime());
}

function safePacketText(value) {
  return !/Bearer\s+|Cookie:|RELEASEFOUNDRY(?:_LABS)?_API_KEY\s*[:=]|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?:\/\/|[A-Za-z]:[\\/](?:Users|home)[\\/]/i.test(String(value));
}

function normalizedDate(value) {
  const date = value instanceof Date ? new Date(value) : new Date(value || Date.now());
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function normalizeScope(value = {}) {
  const nested = value.tenant_scope || value.tenantScope || {};
  return {
    organization_id: value.organization_id || value.organizationId || nested.organization_id || "org-local",
    tenant_id: value.tenant_id || value.tenantId || nested.tenant_id || "tenant-local",
    workspace_id: value.workspace_id || value.workspaceId || nested.workspace_id || "workspace-local",
    project_id: value.project_id || value.projectId || nested.project_id || "project-local",
    environment_id: value.environment_id || value.environmentId || nested.environment_id || "staging"
  };
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortValue(value));
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortValue(item)]));
  }
  return value;
}
