import { createHash } from "node:crypto";

export const A3_MULTIMODAL_REVIEW_ASSIGNMENT_EVENT_SCHEMA_VERSION =
  "a3.multimodal_review_assignment_event.v1";
export const A3_MULTIMODAL_REVIEW_ASSIGNMENT_RECEIPT_SCHEMA_VERSION =
  "a3.multimodal_review_assignment_receipt.v1";

const ACTIONS = new Set(["claim", "renew", "release", "transfer"]);
const EVENT_TYPES = new Set([
  "claimed",
  "reclaimed_after_expiry",
  "renewed",
  "released",
  "transferred"
]);
const PRIVILEGED_ROLES = new Set(["owner", "admin"]);
const INPUT_FIELDS = new Set([
  "action",
  "expected_version",
  "lease_seconds",
  "target_reviewer_hash",
  "reason_code"
]);
const MIN_LEASE_SECONDS = 60;
const MAX_LEASE_SECONDS = 3600;
const DEFAULT_LEASE_SECONDS = 900;

export function buildA3MultimodalReviewAssignmentProjection(queue = {}, events = [], options = {}) {
  const now = normalizedDate(options.now);
  const queueItems = Array.isArray(queue.items) ? queue.items : [];
  const knownQueueIds = new Set(queueItems.map((item) => item.queue_id));
  const validEvents = [];
  let invalidEventCount = 0;

  for (const event of Array.isArray(events) ? events : []) {
    if (validAssignmentEvent(event) && knownQueueIds.has(event.queue_id)) {
      validEvents.push(event);
    } else {
      invalidEventCount += 1;
    }
  }

  const byQueue = groupEventsByQueue(validEvents);
  const items = queueItems.map((item) => ({
    ...item,
    operational_state: assignmentState(byQueue.get(item.queue_id) || [], now)
  }));
  const states = items.map((item) => item.operational_state);
  const activeCount = states.filter((state) => state.status === "claimed").length;
  const expiredCount = states.filter((state) => state.status === "expired").length;
  const unassignedCount = states.filter((state) => state.status === "unassigned").length;

  return {
    ...queue,
    summary: {
      ...(queue.summary || {}),
      assignment_active_count: activeCount,
      assignment_expired_count: expiredCount,
      assignment_unassigned_count: unassignedCount,
      assignment_event_count: validEvents.length,
      assignment_invalid_event_count: invalidEventCount
    },
    assignment_workflow: {
      schema_version: "a3.multimodal_review_assignment_index.v1",
      mode: "append_only_lease_events",
      optimistic_concurrency: "expected_version",
      lease_seconds: {
        default: DEFAULT_LEASE_SECONDS,
        minimum: MIN_LEASE_SECONDS,
        maximum: MAX_LEASE_SECONDS
      },
      active_count: activeCount,
      expired_count: expiredCount,
      unassigned_count: unassignedCount,
      event_count: validEvents.length,
      invalid_event_count: invalidEventCount,
      release_authority: false,
      a2_decision_recomputed: false
    },
    authority_boundary: {
      ...(queue.authority_boundary || {}),
      assignment_events_release_authority: false,
      assignment_events_change_a2_decision: false
    },
    items,
    safety: {
      ...(queue.safety || {}),
      raw_reviewer_identity_exposed: false,
      raw_assignment_payload_exposed: false
    }
  };
}

export function planA3MultimodalReviewAssignmentTransition(queue = {}, events = [], input = {}, context = {}) {
  const details = validateTransitionInput(input, context);
  const queueItem = (Array.isArray(queue.items) ? queue.items : [])
    .find((item) => item.queue_id === context.queueId);
  if (!queueItem) {
    return failure("queue_item_not_found", 404, [{ field: "queue_id", issue: "not_found" }]);
  }
  if (details.length) {
    return failure("invalid_assignment_action", 400, details);
  }

  const now = normalizedDate(context.now);
  const queueEvents = (Array.isArray(events) ? events : [])
    .filter((event) => validAssignmentEvent(event) && event.queue_id === context.queueId);
  const current = assignmentState(queueEvents, now);
  if (input.expected_version !== current.version) {
    return failure("assignment_version_conflict", 409, [{
      field: "expected_version",
      issue: "stale_version",
      expected: current.version
    }]);
  }

  const actorHash = context.actorHash;
  const actorRole = context.actorRole;
  const ownsActiveLease = current.status === "claimed" && current.assigned_reviewer_hash === actorHash;
  const privileged = PRIVILEGED_ROLES.has(actorRole);
  let eventType;
  let assignedReviewerHash;
  let leaseExpiresAt = null;
  const leaseSeconds = normalizedLeaseSeconds(input.lease_seconds);

  if (input.action === "claim") {
    if (current.status === "claimed") {
      return failure("assignment_already_claimed", 409, [{
        field: "queue_id",
        issue: "active_lease_exists",
        current_version: current.version
      }]);
    }
    eventType = current.status === "expired" ? "reclaimed_after_expiry" : "claimed";
    assignedReviewerHash = actorHash;
    leaseExpiresAt = addSeconds(now, leaseSeconds);
  }

  if (input.action === "renew") {
    if (!ownsActiveLease) {
      return failure("assignment_not_owned", 409, [{ field: "queue_id", issue: "active_lease_owned_by_another_reviewer_or_expired" }]);
    }
    eventType = "renewed";
    assignedReviewerHash = actorHash;
    leaseExpiresAt = addSeconds(now, leaseSeconds);
  }

  if (input.action === "release") {
    if (current.status !== "claimed") {
      return failure("assignment_not_active", 409, [{ field: "queue_id", issue: "active_lease_required" }]);
    }
    if (!ownsActiveLease && !privileged) {
      return failure("assignment_not_owned", 403, [{ field: "actor_hash", issue: "assigned_reviewer_or_admin_required" }]);
    }
    eventType = "released";
    assignedReviewerHash = null;
  }

  if (input.action === "transfer") {
    if (current.status !== "claimed") {
      return failure("assignment_not_active", 409, [{ field: "queue_id", issue: "active_lease_required" }]);
    }
    if (!ownsActiveLease && !privileged) {
      return failure("assignment_not_owned", 403, [{ field: "actor_hash", issue: "assigned_reviewer_or_admin_required" }]);
    }
    if (input.target_reviewer_hash === current.assigned_reviewer_hash) {
      return failure("assignment_target_unchanged", 409, [{ field: "target_reviewer_hash", issue: "must_differ_from_current_reviewer" }]);
    }
    eventType = "transferred";
    assignedReviewerHash = input.target_reviewer_hash;
    leaseExpiresAt = addSeconds(now, leaseSeconds);
  }

  const event = createAssignmentEvent({
    queueItem,
    eventType,
    version: current.version + 1,
    actorHash,
    actorRole,
    previousReviewerHash: current.assigned_reviewer_hash,
    assignedReviewerHash,
    leaseExpiresAt,
    reasonCode: input.reason_code || defaultReasonCode(input.action),
    source: context.source,
    tenantScope: context.tenantScope,
    createdAt: now.toISOString()
  });
  const projected = assignmentState([...queueEvents, event], now);
  return {
    valid: true,
    statusCode: 200,
    event,
    operational_state: projected
  };
}

function validateTransitionInput(input, context) {
  const details = [];
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return [{ field: "assignment", issue: "object_required" }];
  }
  for (const field of Object.keys(input)) {
    if (!INPUT_FIELDS.has(field)) details.push({ field, issue: "unexpected_field" });
  }
  if (!ACTIONS.has(input.action)) details.push({ field: "action", issue: "unsupported_action" });
  if (!Number.isInteger(input.expected_version) || input.expected_version < 0) {
    details.push({ field: "expected_version", issue: "non_negative_integer_required" });
  }
  if (!safeIdentityHash(context.actorHash)) details.push({ field: "actor_hash", issue: "server_verified_hash_required" });
  if (!["owner", "admin", "reviewer"].includes(context.actorRole)) {
    details.push({ field: "actor_role", issue: "reviewer_admin_or_owner_required" });
  }
  if (["claim", "renew", "transfer"].includes(input.action)
    && input.lease_seconds !== undefined
    && (!Number.isInteger(input.lease_seconds)
      || input.lease_seconds < MIN_LEASE_SECONDS
      || input.lease_seconds > MAX_LEASE_SECONDS)) {
    details.push({ field: "lease_seconds", issue: `integer_${MIN_LEASE_SECONDS}_to_${MAX_LEASE_SECONDS}_required` });
  }
  if (input.action === "transfer" && !safeIdentityHash(input.target_reviewer_hash)) {
    details.push({ field: "target_reviewer_hash", issue: "hashed_reviewer_identity_required" });
  }
  if (input.action !== "transfer" && input.target_reviewer_hash !== undefined) {
    details.push({ field: "target_reviewer_hash", issue: "only_allowed_for_transfer" });
  }
  if (input.reason_code !== undefined && !/^[a-z0-9_]{3,64}$/.test(String(input.reason_code))) {
    details.push({ field: "reason_code", issue: "lower_snake_case_required" });
  }
  return details;
}

function createAssignmentEvent(input) {
  const scope = normalizeScope(input.tenantScope);
  const body = {
    schema_version: A3_MULTIMODAL_REVIEW_ASSIGNMENT_EVENT_SCHEMA_VERSION,
    source: input.source || "unknown",
    ...scope,
    tenant_scope: scope,
    queue_id: input.queueItem.queue_id,
    case_id: input.queueItem.case_id,
    comparison_hash: input.queueItem.comparison_hash,
    event_type: input.eventType,
    version: input.version,
    actor_hash: input.actorHash,
    actor_role: input.actorRole,
    previous_reviewer_hash: input.previousReviewerHash || null,
    assigned_reviewer_hash: input.assignedReviewerHash || null,
    lease_started_at: input.leaseExpiresAt ? input.createdAt : null,
    lease_expires_at: input.leaseExpiresAt,
    reason_code: input.reasonCode,
    created_at: input.createdAt,
    release_authority: false,
    a2_decision_recomputed: false,
    safety: {
      raw_reviewer_identity_included: false,
      raw_model_payload_included: false,
      raw_media_included: false,
      signed_url_included: false,
      secret_values_included: false
    }
  };
  const digest = sha256(stableJson(body));
  return {
    ...body,
    event_id: `mmra_${digest.slice(0, 20)}`,
    event_hash: `sha256:${digest}`
  };
}

function assignmentState(events, now) {
  const sorted = [...events].sort((left, right) => (
    Number(left.version) - Number(right.version)
      || String(left.created_at).localeCompare(String(right.created_at))
  ));
  const latest = sorted.at(-1);
  if (!latest) return emptyAssignmentState();
  const released = latest.event_type === "released" || !latest.assigned_reviewer_hash;
  const expiresAt = latest.lease_expires_at ? new Date(latest.lease_expires_at) : null;
  const expired = !released && expiresAt && expiresAt.getTime() <= now.getTime();
  const status = released ? "unassigned" : expired ? "expired" : "claimed";
  return {
    schema_version: "a3.multimodal_review_operational_state.v1",
    status,
    version: latest.version,
    assigned_reviewer_hash: latest.assigned_reviewer_hash,
    previous_reviewer_hash: latest.previous_reviewer_hash,
    lease_started_at: latest.lease_started_at,
    lease_expires_at: latest.lease_expires_at,
    last_action: latest.event_type,
    last_action_at: latest.created_at,
    reason_code: latest.reason_code,
    event_count: sorted.length,
    lock_active: status === "claimed",
    can_be_claimed: status !== "claimed",
    authoritative_disposition_recorded: false,
    release_authority: false,
    a2_decision_recomputed: false
  };
}

function emptyAssignmentState() {
  return {
    schema_version: "a3.multimodal_review_operational_state.v1",
    status: "unassigned",
    version: 0,
    assigned_reviewer_hash: null,
    previous_reviewer_hash: null,
    lease_started_at: null,
    lease_expires_at: null,
    last_action: null,
    last_action_at: null,
    reason_code: null,
    event_count: 0,
    lock_active: false,
    can_be_claimed: true,
    authoritative_disposition_recorded: false,
    release_authority: false,
    a2_decision_recomputed: false
  };
}

function validAssignmentEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) return false;
  return event.schema_version === A3_MULTIMODAL_REVIEW_ASSIGNMENT_EVENT_SCHEMA_VERSION
    && typeof event.queue_id === "string"
    && EVENT_TYPES.has(event.event_type)
    && Number.isInteger(event.version)
    && event.version > 0
    && safeIdentityHash(event.actor_hash)
    && typeof event.created_at === "string"
    && !Number.isNaN(new Date(event.created_at).getTime())
    && event.release_authority === false
    && event.a2_decision_recomputed === false;
}

function groupEventsByQueue(events) {
  const grouped = new Map();
  for (const event of events) {
    const queue = grouped.get(event.queue_id) || [];
    queue.push(event);
    grouped.set(event.queue_id, queue);
  }
  return grouped;
}

function failure(error, statusCode, details) {
  return { valid: false, error, statusCode, details };
}

function safeIdentityHash(value) {
  const text = String(value || "");
  return /^[A-Za-z0-9:_-]{8,160}$/.test(text)
    && !/bearer|cookie|secret|token|password|@|https?:/i.test(text);
}

function normalizedLeaseSeconds(value) {
  return value === undefined ? DEFAULT_LEASE_SECONDS : value;
}

function normalizedDate(value) {
  const date = value instanceof Date ? new Date(value) : new Date(value || Date.now());
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function addSeconds(date, seconds) {
  return new Date(date.getTime() + seconds * 1000).toISOString();
}

function defaultReasonCode(action) {
  return {
    claim: "manual_review_claim",
    renew: "active_review_renewal",
    release: "reviewer_release",
    transfer: "reviewer_handoff"
  }[action] || "review_workflow_action";
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
