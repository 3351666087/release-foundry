import { createHash } from "node:crypto";

import { buildA3TenantScope } from "./a3_tenant_scope.mjs";

export const A3_EVENT_ENVELOPE_SCHEMA_VERSION = "ashr.event_envelope.v1";

export function buildA3EventEnvelope(input = {}, options = {}) {
  const tenantScope = buildA3TenantScope(input.tenant_scope || input.tenantScope || {}, options);
  const payload = sanitizePayload(input.payload || {});
  const payloadHash = sha256(stableJson(payload));
  const resourceType = input.resource_type || input.resourceType || "unknown";
  const resourceId = input.resource_id || input.resourceId || "unknown";
  const eventType = input.event_type || input.eventType || "unknown.event";
  const createdAt = input.created_at || input.createdAt || options.createdAt || "2026-07-09T00:00:00.000Z";
  const requestId = input.request_id || input.requestId || options.requestId || "req-local";
  const traceId = input.trace_id || input.traceId || options.traceId || "trace-local";
  const actorId = input.actor_id || input.actorId || options.actorId || "actor-system";
  const eventSeed = stableJson({
    eventType,
    resourceType,
    resourceId,
    payloadHash,
    createdAt,
    requestId,
    traceId,
    tenantScope
  });

  return {
    schema_version: A3_EVENT_ENVELOPE_SCHEMA_VERSION,
    event_id: input.event_id || input.eventId || `evt_${sha256(eventSeed).slice(0, 16)}`,
    event_type: eventType,
    organization_id: tenantScope.organization_id,
    tenant_id: tenantScope.tenant_id,
    workspace_id: tenantScope.workspace_id,
    project_id: tenantScope.project_id,
    environment_id: tenantScope.environment_id,
    actor_id: actorId,
    request_id: requestId,
    trace_id: traceId,
    resource_type: resourceType,
    resource_id: resourceId,
    created_at: createdAt,
    payload_ref: input.payload_ref || input.payloadRef || null,
    payload_hash: input.payload_hash || input.payloadHash || payloadHash,
    redaction_status: input.redaction_status || input.redactionStatus || "metadata_only",
    payload_inline: false,
    payload_schema_version: payload.schema_version || input.payload_schema_version || null,
    usage_meter: input.usage_meter || input.usageMeter || null,
    audit_visibility: "metadata_only",
    safety: {
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_signed_urls_allowed: false
    }
  };
}

export function validateA3EventEnvelope(event = {}) {
  const errors = [];
  for (const field of [
    "event_id",
    "event_type",
    "schema_version",
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "actor_id",
    "request_id",
    "trace_id",
    "resource_type",
    "resource_id",
    "created_at",
    "payload_hash",
    "redaction_status"
  ]) {
    if (!event[field]) {
      errors.push(`${field} is required`);
    }
  }
  if (event.schema_version !== A3_EVENT_ENVELOPE_SCHEMA_VERSION) {
    errors.push("schema_version must be ashr.event_envelope.v1");
  }
  if (!/^[a-f0-9]{64}$/.test(String(event.payload_hash || ""))) {
    errors.push("payload_hash must be a sha256 hex digest");
  }
  if (JSON.stringify(event).match(/Bearer\s+[A-Za-z0-9._-]+|Cookie:|X-Amz-Signature=|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i)) {
    errors.push("event envelope contains sensitive-looking material");
  }
  return { valid: errors.length === 0, errors };
}

function sanitizePayload(payload = {}) {
  return JSON.parse(JSON.stringify(payload, (key, value) => {
    if (/authorization|cookie|secret|token|password|api_key|signed_url|email/i.test(key)) {
      return "[REDACTED]";
    }
    if (typeof value === "string") {
      return value
        .replace(/\bBearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer [REDACTED]")
        .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]")
        .replace(/https:\/\/[^"\s]+X-Amz-Signature=[^"\s]+/gi, "[REDACTED_SIGNED_URL]");
    }
    return value;
  }));
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortForStableJson(item)]));
  }
  return value;
}
