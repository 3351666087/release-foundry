#!/usr/bin/env node
import { AGENT_INPUT_PART_TYPES, AGENT_INPUT_SCHEMA_VERSION, CloudApiService, NotFoundError, ValidationError, coerceAgentInput } from "./index.js";
import { resolve } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { BillingLedger, buildBillingPortalPlan, buildCheckoutSessionPlan, verifyBillingWebhookEnvelope } from "./billing.js";
import {
  AccountConnectionHttpClient,
  assertPublicAccountConnectionPayload,
  normalizeAccountConnectionProvider,
  parseAccountConnection,
  parseAccountConnectionDisconnect,
  parseAccountConnectionStart,
} from "./account-connections.js";
import type { AgentInput, AgentInputPart, JsonRecord } from "./index.js";

export const CONTROL_PLANE_SCHEMA_VERSION = "ashr.clone.saas_control_plane.v1";
export const SAAS_CLIENT_VERSION = "ashr.clone.ts_saas_ingestion_client.v1";
export const SAAS_OPENAPI_SCHEMA_VERSION = "ashr.clone.saas_openapi.v1";
export const CONTROL_PLANE_OPENAPI_VERSION = "3.0.3";
export const MUTATING_CALIBRATION_INDEX_SCHEMA_VERSION = "ashr.clone.official_api_mutating_calibration_index.v1";
export const MUTATING_CALIBRATION_MODALITIES = ["text", "image", "audio", "file", "video"] as const;
export const SAAS_QUOTA_LIMITS: Record<string, number> = {
  "api_key.create": 100,
  "run.upload": 10000,
  "sdk.submit": 10000,
  "trace.ingest": 100000,
  "artifact.manifest": 10000,
  "worker.job.enqueue": 100000,
  "worker.job.lease": 100000,
  "worker.job.complete": 100000,
  "worker.job.fail": 100000,
  "audit_chain.verify": 10000,
  "release_evidence.verify": 10000,
};

export const API_KEY_ADMIN_SCOPE = "api_key:write";
export const API_KEY_READ_SCOPE = "api_key:read";
export const RUN_CREATE_SCOPE = "run:create";
export const RUN_UPLOAD_SCOPE = "run:upload";
export const TRACE_INGEST_SCOPE = "trace:ingest";
export const ARTIFACT_MANIFEST_SCOPE = "artifact:upload";
export const COMMERCIAL_CONFIG_WRITE_SCOPE = "commercial:write";
export const ADMIN_ALL_SCOPE = "admin:all";
export const USAGE_READ_SCOPE = "usage:read";
export const AUDIT_READ_SCOPE = "audit:read";
export const BILLING_READ_SCOPE = "billing:read";
export const BILLING_WRITE_SCOPE = "billing:write";
export const BILLING_WEBHOOK_SCOPE = "billing:webhook";
export const WORKER_JOB_READ_SCOPE = "worker_job:read";
export const WORKER_JOB_WRITE_SCOPE = "worker_job:write";

const SCOPE_ALIASES: Record<string, string[]> = {
  "key:admin": [API_KEY_ADMIN_SCOPE, API_KEY_READ_SCOPE],
  "key:read": [API_KEY_READ_SCOPE],
  "sdk:submit": [RUN_CREATE_SCOPE],
  "runs:write": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"],
  "write:runs": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"],
  "traces:write": [TRACE_INGEST_SCOPE],
  "artifact:write": [ARTIFACT_MANIFEST_SCOPE],
  "artifacts:write": [ARTIFACT_MANIFEST_SCOPE],
  "worker:read": [WORKER_JOB_READ_SCOPE],
  "worker:write": [WORKER_JOB_READ_SCOPE, WORKER_JOB_WRITE_SCOPE],
  "billing:admin": [BILLING_READ_SCOPE, BILLING_WRITE_SCOPE, BILLING_WEBHOOK_SCOPE],
  "billing:write": [BILLING_READ_SCOPE],
  "queue:read": [WORKER_JOB_READ_SCOPE],
  "queue:write": [WORKER_JOB_READ_SCOPE, WORKER_JOB_WRITE_SCOPE],
  [API_KEY_ADMIN_SCOPE]: [API_KEY_READ_SCOPE],
  [ADMIN_ALL_SCOPE]: ["*"],
};

export const HOSTED_ROUTE_SCOPE_REQUIREMENTS: Record<string, string[]> = {
  "GET /v1/accounts/{account_id}": ["identity:read"],
  "GET /v1/accounts/{account_id}/credentials": ["identity:read"],
  "GET /v1/accounts/{account_id}/memberships": ["identity:read"],
  "GET /v1/projects/{project_id}/api-keys": [API_KEY_READ_SCOPE],
  "GET /v1/projects/{project_id}/api-keys/rate-limits": [],
  "GET /v1/projects/{project_id}/audit-log": [AUDIT_READ_SCOPE],
  "GET /v1/projects/{project_id}/billing/ledger": [BILLING_READ_SCOPE],
  "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": ["evidence:read"],
  "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle": ["run:lifecycle:read"],
  "GET /v1/projects/{project_id}/runs/{run_id}/release-evidence": ["evidence:read"],
  "GET /v1/projects/{project_id}/quota": [USAGE_READ_SCOPE],
  "GET /v1/projects/{project_id}/usage": [USAGE_READ_SCOPE],
  "POST /v1/projects/{project_id}/quota/limits": [USAGE_READ_SCOPE],
  "POST /v1/projects/{project_id}/usage/quotas": [USAGE_READ_SCOPE],
  "GET /v1/projects/{project_id}/worker-jobs": [WORKER_JOB_READ_SCOPE],
  "POST /v1/bootstrap": [],
  "POST /v1/projects/{project_id}/api-keys": [API_KEY_ADMIN_SCOPE],
  "POST /v1/projects/{project_id}/api-keys/{key_id}/authenticate": [],
  "POST /v1/projects/{project_id}/api-keys/{key_id}/rate-limit": [API_KEY_ADMIN_SCOPE],
  "POST /v1/projects/{project_id}/api-keys/{key_id}/revoke": [API_KEY_ADMIN_SCOPE],
  "POST /v1/projects/{project_id}/api-keys/{key_id}/verify": [],
  "POST /v1/projects/{project_id}/audit-chain/verify": [AUDIT_READ_SCOPE],
  "POST /v1/projects/{project_id}/billing/checkout-plan": [BILLING_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/billing/portal-plan": [BILLING_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/billing/webhooks/ingest": [BILLING_WEBHOOK_SCOPE],
  "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-providers/configure": [COMMERCIAL_CONFIG_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/begin": [COMMERCIAL_CONFIG_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/{flow_id}/complete": [COMMERCIAL_CONFIG_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": [ARTIFACT_MANIFEST_SCOPE],
  "POST /v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": ["evidence:read"],
  "POST /v1/projects/{project_id}/runs/{run_id}/release-gate": [AUDIT_READ_SCOPE],
  "POST /v1/projects/{project_id}/runs/{run_id}/trace-events": [TRACE_INGEST_SCOPE],
  "POST /v1/projects/{project_id}/runs/{run_id}/upload": [RUN_UPLOAD_SCOPE],
  "POST /v1/projects/{project_id}/sdk-submit": ["sdk:submit"],
  "POST /v1/projects/{project_id}/worker-jobs/enqueue": [WORKER_JOB_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/worker-jobs/lease": [WORKER_JOB_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete": [WORKER_JOB_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail": [WORKER_JOB_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat": [WORKER_JOB_WRITE_SCOPE],
  "POST /v1/projects/{project_id}/oauth/{provider}/start": ["oauth:connect"],
  "GET /v1/projects/{project_id}/oauth/{provider}/connection": ["oauth:read"],
  "POST /v1/projects/{project_id}/oauth/{provider}/disconnect": ["oauth:disconnect"],
  "POST /v1/projects/{project_id}/oauth/github/start": ["oauth:connect"],
  "GET /v1/projects/{project_id}/oauth/github/connection": ["oauth:read"],
  "POST /v1/projects/{project_id}/oauth/github/disconnect": ["oauth:disconnect"],
  "POST /v1/projects/{project_id}/oauth/google/start": ["oauth:connect"],
  "GET /v1/projects/{project_id}/oauth/google/connection": ["oauth:read"],
  "POST /v1/projects/{project_id}/oauth/google/disconnect": ["oauth:disconnect"],
};

export const UNSUPPORTED_GO_ROUTE_GAPS: Record<string, { reason: string; replacement_route?: string; consumer_action: string }> = {
  "GET /health": {
    reason: "Go exposes a root health alias; the hosted TS client uses scoped SaaS/OpenAPI helpers instead of consuming this alias.",
    replacement_route: "GET /healthz",
    consumer_action: "keep unsupported until the generated Go OpenAPI marks root health aliases as public client surface",
  },
  "GET /healthz": {
    reason: "The TS router exposes this local health helper, but the route/scope manifest tracks project-scoped hosted API calls.",
    consumer_action: "keep unsupported as an unscoped adapter helper outside hosted route authorization",
  },
  "GET /openapi.json": {
    reason: "The TS router exposes this local OpenAPI helper, but hosted route scope parity covers project-scoped API calls.",
    consumer_action: "keep unsupported as an unscoped adapter helper outside hosted route authorization",
  },
  "GET /v1/healthz": {
    reason: "Go exposes a versioned health alias that is not part of the TS/Python shared hosted ingestion surface.",
    replacement_route: "GET /healthz",
    consumer_action: "keep unsupported until versioned health aliases become SDK contract routes",
  },
  "GET /v1/openapi.json": {
    reason: "The TS router exposes this local OpenAPI helper, but hosted route scope parity covers project-scoped API calls.",
    consumer_action: "keep unsupported as an unscoped adapter helper outside hosted route authorization",
  },
  "GET /oauth/github/callback": {
    reason: "Go exposes the canonical localhost GitHub account-connection callback; the hosted TypeScript route client does not execute browser redirects.",
    consumer_action: "keep explicit until the shared generated OpenAPI client models provider callbacks without exposing authorization codes",
  },
  "GET /v1/projects/{project_id}/audit-chain/verify": {
    reason: "Go has a read-style audit-chain verifier route while hosted clients consume the POST verifier contract.",
    replacement_route: "POST /v1/projects/{project_id}/audit-chain/verify",
    consumer_action: "keep unsupported until Go and hosted clients settle on one audit-chain verification method",
  },
  "POST /bootstrap": {
    reason: "Go keeps a root bootstrap alias; hosted clients consume the versioned bootstrap route.",
    replacement_route: "POST /v1/bootstrap",
    consumer_action: "keep unsupported until root bootstrap aliases are part of generated SDK contracts",
  },
  "POST /v1/projects/{project_id}/api-keys/preflight": {
    reason: "Go advertises an API-key preflight route that TS/Python hosted clients have not implemented yet.",
    consumer_action: "keep unsupported until preflight request and response semantics are added to both hosted SDKs",
  },
  "GET /v1/projects/{project_id}/oauth/github/start": {
    reason: "Go exposes a browser redirect alias; hosted SDKs use the provider-neutral JSON POST start contract.",
    replacement_route: "POST /v1/projects/{project_id}/oauth/{provider}/start",
    consumer_action: "keep explicit as a browser-only alias outside the hosted JSON client",
  },
  "DELETE /v1/projects/{project_id}/oauth/github/disconnect": {
    reason: "Go exposes an idempotent HTTP DELETE alias; hosted SDKs use the provider-neutral JSON POST disconnect contract.",
    replacement_route: "POST /v1/projects/{project_id}/oauth/{provider}/disconnect",
    consumer_action: "keep explicit as a method alias outside the hosted JSON client",
  },
  "GET /oauth/google/callback": {
    reason: "Go exposes the canonical localhost Google account-connection callback; the hosted TypeScript route client does not execute browser redirects.",
    consumer_action: "keep explicit until the generated OpenAPI client models provider callbacks without exposing authorization codes",
  },
  "GET /v1/projects/{project_id}/oauth/google/start": {
    reason: "Go exposes a browser redirect alias; hosted SDKs use the provider-neutral JSON POST start contract.",
    replacement_route: "POST /v1/projects/{project_id}/oauth/{provider}/start",
    consumer_action: "keep explicit as a browser-only alias outside the hosted JSON client",
  },
  "DELETE /v1/projects/{project_id}/oauth/google/disconnect": {
    reason: "Go exposes an idempotent HTTP DELETE alias; hosted SDKs use the provider-neutral JSON POST disconnect contract.",
    replacement_route: "POST /v1/projects/{project_id}/oauth/{provider}/disconnect",
    consumer_action: "keep explicit as a method alias outside the hosted JSON client",
  },
  "POST /v1/projects/{project_id}/runs/submit": {
    reason: "Go keeps an older run submit shape while hosted clients submit through the SDK submission contract.",
    replacement_route: "POST /v1/projects/{project_id}/sdk-submit",
    consumer_action: "keep unsupported until run submit is either removed from Go or added to both hosted SDKs deliberately",
  },
  "GET /v1/projects/{project_id}/billing/payments/bills": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/bills/{provider}/{bill_entry_id}": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/notifications": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/notifications/{provider}/{event_id}": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/orders": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/orders/{provider}/{merchant_order_id}": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/providers": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/refunds": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/payments/refunds/{provider}/{merchant_refund_id}": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/reconciliation/events": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "GET /v1/projects/{project_id}/billing/reconciliation/events/{provider}/{event_id}": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "POST /v1/projects/{project_id}/billing/payments/bills": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "POST /v1/projects/{project_id}/billing/payments/notifications": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "POST /v1/projects/{project_id}/billing/payments/orders": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "POST /v1/projects/{project_id}/billing/payments/refunds": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
  "POST /v1/projects/{project_id}/billing/reconciliation/events": {
    reason: "Go owns the Round47 China payment and reconciliation runtime; the TypeScript hosted SDK contract is not implemented yet.",
    consumer_action: "keep the route explicit in parity evidence until the hosted SDK implements the provider-safe China payment contract",
  },
};

export interface SaaSControlPlaneStore {
  api_keys: Record<string, JsonRecord>;
  api_key_rate_limits: Record<string, JsonRecord>;
  uploads: Record<string, JsonRecord>;
  trace_batches: Record<string, JsonRecord>;
  sdk_submissions: Record<string, JsonRecord>;
  audit_log: Record<string, JsonRecord>;
  usage_ledger: Record<string, JsonRecord>;
  idempotency_keys: Record<string, JsonRecord>;
  artifact_manifests: Record<string, JsonRecord>;
  worker_jobs: Record<string, JsonRecord>;
  oauth_provider_configs: Record<string, JsonRecord>;
  oauth_authorization_flows: Record<string, JsonRecord>;
  oauth_sessions: Record<string, JsonRecord>;
}

export interface SaaSControlPlaneState extends JsonRecord {
  schema_version: typeof CONTROL_PLANE_SCHEMA_VERSION;
  state_schema_version: number;
  cloud: JsonRecord;
  metadata: { local_only: true; ashr_api_used: false };
  state_metadata: JsonRecord;
  control_plane: SaaSControlPlaneStore;
  billing_ledger?: JsonRecord;
  integrity: JsonRecord;
}

export interface SaaSRouterResponse extends JsonRecord {
  status_code: number;
  body: JsonRecord;
}

export type SaaSClientOperation =
  | "bootstrap_project"
  | "create_api_key"
  | "verify_api_key_secret"
  | "configure_api_key_rate_limit"
  | "api_key_rate_limit_snapshot"
  | "list_api_keys"
  | "revoke_api_key"
  | "sdk_submit"
  | "upload_run"
  | "ingest_trace"
  | "lifecycle"
  | "lifecycle_snapshot"
  | "usage"
  | "usage_snapshot"
  | "quota_snapshot"
  | "billing_checkout_plan"
  | "billing_portal_plan"
  | "billing_webhook_ingest"
  | "billing_ledger"
  | "audit_log"
  | "audit_chain_verify"
  | "release_gate"
  | "release_evidence"
  | "release_evidence_verify"
  | "artifact_manifest"
  | "artifact_manifests"
  | "configure_oauth_provider"
  | "oauth_authorization_begin"
  | "oauth_authorization_complete"
  | "worker_job_enqueue"
  | "worker_job_lease"
  | "worker_job_heartbeat"
  | "worker_job_complete"
  | "worker_job_fail"
  | "worker_jobs";

export interface SaaSClientEnvelope<T extends JsonRecord = JsonRecord, O extends SaaSClientOperation = SaaSClientOperation> extends JsonRecord {
  schema_version: typeof CONTROL_PLANE_SCHEMA_VERSION;
  client_version: typeof SAAS_CLIENT_VERSION;
  operation: O;
  result: T;
}

export interface SaaSMediaEnvelope extends JsonRecord {
  schema_version: typeof CONTROL_PLANE_SCHEMA_VERSION;
  agent_input_schema_version: typeof AGENT_INPUT_SCHEMA_VERSION;
  text: string;
  parts: AgentInputPart[];
  metadata: JsonRecord;
  raw_payload_included: false;
  secret_value_present: false;
}

export interface SaaSSdkSubmitResult extends JsonRecord { submission: JsonRecord; run: JsonRecord; }
export interface SaaSUploadRunResult extends JsonRecord { upload_id: string; payload_sha256: string; payload_keys: string[]; raw_payload_included: false; }
export interface SaaSTraceIngestResult extends JsonRecord { batch_id: string; observation_count: number; observation_ids: string[]; raw_payload_included: false; }
export interface SaaSApiKeyRecord extends JsonRecord { tenant_id: string; project_id: string; key_id: string; name: string; prefix: string; secret_hash_present: boolean; secret_value_present: boolean; status: string; scopes: string[]; }
export interface SaaSApiKeyCreateResult extends SaaSApiKeyRecord { one_time_secret?: string; one_time_secret_displayed: boolean; }
export interface SaaSApiKeyListResult extends JsonRecord { api_keys: SaaSApiKeyRecord[]; }
export interface SaaSApiKeyVerificationResult extends JsonRecord { tenant_id: string; project_id: string; key_id: string; verified?: boolean; authenticated?: boolean; secret_value_present: false; api_key: SaaSApiKeyRecord; }
export interface SaaSApiKeyRateLimit extends JsonRecord { tenant_id: string; project_id: string; key_id: string; operation: string; period: string; limit: number; used: number; remaining: number; }
export interface SaaSApiKeyRateLimitSnapshot extends JsonRecord { tenant_id: string; project_id: string; key_id: string | null; rate_limits: SaaSApiKeyRateLimit[]; }
export interface SaaSQuotaSnapshotResult extends JsonRecord { tenant_id: string; project_id: string; events: JsonRecord[]; totals: Record<string, number>; quota: JsonRecord; }
export interface SaaSArtifactManifestResult extends JsonRecord { artifact_id: string; tenant_id: string; project_id: string; run_id: string; manifest_schema_version: string; manifest_keys: string[]; manifest_sha256: string; raw_manifest_included: false; }
export interface SaaSArtifactManifestListResult extends JsonRecord { artifact_manifests: SaaSArtifactManifestResult[]; }
export interface SaaSBillingCheckoutPlan extends JsonRecord { plan_type: "checkout_session"; plan_id: string; provider: string; mode: string; tenant_id: string; project_id: string; customer_ref: string; provider_request: JsonRecord; side_effects: { provider_called: false; checkout_or_portal_called: false; real_charge_possible: false }; }
export interface SaaSBillingPortalPlan extends JsonRecord { plan_type: "billing_portal"; plan_id: string; provider: "stripe"; mode: string; tenant_id: string; project_id: string; customer_ref: string; return_url: string; provider_request: JsonRecord; side_effects: { provider_called: false; checkout_or_portal_called: false; real_charge_possible: false }; }
export interface SaaSBillingWebhookEnvelope extends JsonRecord { plan_type: "webhook_envelope_verification"; provider: string; mode: string; tenant_id: string; project_id: string; event_type: string; event_id: string; payload_sha256: string; signature_header_present: boolean; verified: boolean; failures: Array<{ reason: string }>; raw_payload_included: false; secret_value_present: false; }
export interface SaaSBillingWebhookIngestResult extends JsonRecord { provider_event_key: string; provider: string; mode: string; tenant_id: string; project_id: string; event_id: string; event_type: string; payload_sha256: string; ledger_event_id?: string; ledger_event_type?: string; ingest_status: "accepted" | "duplicate" | "conflict"; ledger_mutation_count: number; raw_payload_included: false; secret_value_present: false; }
export interface SaaSOAuthProviderConfig extends JsonRecord { tenant_id: string; project_id: string; provider: "github" | "google"; config_id: string; client_id_ref: string; client_secret_ref: string; redirect_uris: string[]; scopes: string[]; enabled: boolean; secret_value_present: false; }
export type SaaSOAuthAuthorizationStatus = "pending" | "failed" | "completed";
export interface SaaSOAuthAuthorizationFlow extends JsonRecord { tenant_id: string; project_id: string; flow_id: string; provider: string; provider_config_id: string; redirect_uri: string; state_hash_present: boolean; code_challenge: string; code_challenge_method: "S256"; status: SaaSOAuthAuthorizationStatus; session_id: string | null; provider_code_ref_present: boolean; failure_reasons: string[]; secret_value_present: false; raw_code_present: false; raw_state_present: false; }
export interface SaaSOAuthAuthorizationBeginResult extends SaaSOAuthAuthorizationFlow { state: string; }
export interface SaaSOAuthSession extends JsonRecord { tenant_id: string; project_id: string; session_id: string; provider: "github" | "google"; provider_config_id: string; subject_ref: string; access_token_ref_present: boolean; refresh_token_ref_present: boolean; status: "active"; secret_value_present: false; }
export interface SaaSOAuthAuthorizationCompleteResult extends SaaSOAuthAuthorizationFlow { accepted: boolean; session?: SaaSOAuthSession; }
export interface SaaSOAuthProviderConfigureOptions { provider: string; clientIdRef: string; clientSecretRef: string; redirectUris: string[]; scopes: string[]; configId?: string; authKeyId?: string; }
export interface SaaSOAuthAuthorizationBeginOptions { providerConfigId: string; redirectUri: string; codeVerifier: string; state?: string; authKeyId?: string; }
export interface SaaSOAuthAuthorizationCompleteOptions { flowId: string; state: string; codeVerifier: string; redirectUri: string; subjectRef: string; providerCodeRef?: string; providerError?: string; accessTokenRef?: string; refreshTokenRef?: string; sessionId?: string; authKeyId?: string; }
export interface SaaSBillingCheckoutOptions extends SaaSClientOptions { customerRef: string; price: JsonRecord; successUrl: string; cancelUrl: string; providerConfig?: JsonRecord; usageRollup?: JsonRecord; metadata?: JsonRecord; idempotencyKey?: string; authKeyId?: string; }
export interface SaaSBillingPortalOptions extends SaaSClientOptions { customerRef: string; returnUrl: string; providerConfig?: JsonRecord; idempotencyKey?: string; authKeyId?: string; }
export interface SaaSBillingWebhookOptions extends SaaSClientOptions { provider: string; mode: string; eventType: string; eventId: string; payloadSha256: string; signatureHeaderPresent: boolean; webhookSecretRef?: string; livemode?: boolean; customerRef?: string; amountMinor?: number; currency?: string; invoiceRef?: string; usageUnits?: number; metadata?: JsonRecord; authKeyId?: string; }

export type SaaSFetchLike = (input: string | URL, init?: {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}) => Promise<{ ok: boolean; status: number; json(): Promise<unknown>; text(): Promise<string> }>;

type SaaSClientOptions = JsonRecord & {
  apiKey?: string;
  api_key?: string;
  bearerApiKey?: string;
  bearer_api_key?: string;
  apiKeySecret?: string;
  api_key_secret?: string;
  apiKeyId?: string;
  api_key_id?: string;
  authKeyId?: string;
  auth_key_id?: string;
  keyId?: string;
  key_id?: string;
  runId?: string;
  run_id?: string;
  datasetId?: string;
  dataset_id?: string;
  agentRef?: string;
  agent_ref?: string;
  uploadId?: string;
  upload_id?: string;
  batchId?: string;
  batch_id?: string;
  idempotencyKey?: string;
  idempotency_key?: string;
  requestId?: string;
  request_id?: string;
  revealSecret?: boolean;
  reveal_secret?: boolean;
  actionPrefix?: string;
  action_prefix?: string;
};

export interface SaaSHttpTransportOptions {
  baseUrl: string;
  fetch?: SaaSFetchLike;
  headers?: Record<string, string>;
  bearerApiKey?: string;
  apiKeySecret?: string;
}

export interface SaaSClientTransport {
  requestJson(method: string, path: string, body?: JsonRecord, options?: { headers?: Record<string, string> }): Promise<JsonRecord>;
}

export function createSaaSControlPlaneStore(seed: Partial<SaaSControlPlaneStore> = {}): SaaSControlPlaneStore {
  return {
    api_keys: { ...(seed.api_keys ?? {}) },
    api_key_rate_limits: { ...(seed.api_key_rate_limits ?? {}) },
    uploads: { ...(seed.uploads ?? {}) },
    trace_batches: { ...(seed.trace_batches ?? {}) },
    sdk_submissions: { ...(seed.sdk_submissions ?? {}) },
    audit_log: { ...(seed.audit_log ?? {}) },
    usage_ledger: { ...(seed.usage_ledger ?? {}) },
    idempotency_keys: { ...(seed.idempotency_keys ?? {}) },
    artifact_manifests: { ...(seed.artifact_manifests ?? {}) },
    worker_jobs: { ...(seed.worker_jobs ?? {}) },
    oauth_provider_configs: { ...(seed.oauth_provider_configs ?? {}) },
    oauth_authorization_flows: { ...(seed.oauth_authorization_flows ?? {}) },
    oauth_sessions: { ...(seed.oauth_sessions ?? {}) },
  };
}

export class SaaSControlPlaneService {
  readonly cloud: CloudApiService;
  readonly store: SaaSControlPlaneStore;
  readonly billingLedger: BillingLedger;

  constructor(options: { cloud?: CloudApiService; store?: Partial<SaaSControlPlaneStore> } = {}) {
    this.cloud = options.cloud ?? new CloudApiService();
    this.store = createSaaSControlPlaneStore(options.store);
    this.billingLedger = new BillingLedger();
  }

  restoreBillingLedgerState(state: JsonRecord = {}): void {
    this.billingLedger.ledgerEvents.length = 0;
    for (const event of Array.isArray(state.ledger_events) ? state.ledger_events : []) {
      if (isRecord(event)) this.billingLedger.ledgerEvents.push(cloneJson(event) as JsonRecord);
    }
    this.billingLedger.providerEvents.clear();
    const providerEvents = isRecord(state.provider_events) ? Object.values(state.provider_events) : (Array.isArray(state.provider_events) ? state.provider_events : []);
    for (const event of providerEvents) {
      if (!isRecord(event)) continue;
      const key = `${event.tenant_id}:${event.project_id}:${event.provider}:${event.mode}:${event.event_id ?? event.provider_event_id}`;
      this.billingLedger.providerEvents.set(key, cloneJson(event) as JsonRecord);
    }
    this.billingLedger.billingAccounts.clear();
    const accounts = isRecord(state.billing_accounts) ? Object.values(state.billing_accounts) : (Array.isArray(state.billing_accounts) ? state.billing_accounts : []);
    for (const account of accounts) {
      if (!isRecord(account)) continue;
      const key = `${account.tenant_id}:${account.project_id}:${account.provider}:${account.mode}:${account.customer_ref}`;
      this.billingLedger.billingAccounts.set(key, cloneJson(account) as JsonRecord);
    }
  }

  billingLedgerState(): JsonRecord {
    return {
      ledger_events: cloneJson(this.billingLedger.ledgerEvents) as JsonRecord[],
      provider_events: Object.fromEntries([...this.billingLedger.providerEvents.entries()].map(([key, value]) => [key, cloneJson(value) as JsonRecord])),
      billing_accounts: Object.fromEntries([...this.billingLedger.billingAccounts.entries()].map(([key, value]) => [key, cloneJson(value) as JsonRecord])),
      raw_payload_included: false,
      secret_value_present: false,
    };
  }

  bootstrapProject(options: { tenantName: string; projectName: string; tenantId?: string; projectId?: string }): JsonRecord {
    const tenant = this.cloud.createTenant(options.tenantName, { tenantId: options.tenantId });
    const project = this.cloud.createProject(tenant.tenant_id, options.projectName, { projectId: options.projectId });
    this.cloud.quota.configure(tenant.tenant_id, project.project_id, SAAS_QUOTA_LIMITS);
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, tenant, project, quota: this.cloud.quotaSnapshot(tenant.tenant_id, project.project_id) };
  }

  createApiKey(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; revealSecret?: boolean }): JsonRecord {
    const project = this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const scopes = options.scopes.map((scope) => normalizeScope(scope));
    if (scopes.length === 0) {
      throw new ValidationError("api key scopes must not be empty");
    }
    this.cloud.quota.consume(project.tenant_id, project.project_id, "api_key.create");
    const keyId = options.keyId ?? newId("key");
    if (this.store.api_keys[keyId] !== undefined) {
      throw new ValidationError(`api key already exists: ${keyId}`);
    }
    const syntheticSecret = `ashr_local_${keyId}_${randomUUID().replaceAll("-", "")}`;
    const now = utcNow();
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      key_id: keyId,
      name: options.name,
      prefix: "ashr_local_***",
      secret_hash_sha256: secretHash(syntheticSecret),
      secret_value_present: false,
      one_time_secret_displayed: options.revealSecret === true,
      verify_mode: "sha256",
      status: "active",
      scopes,
      created_at: now,
      revoked_at: null,
      last_used_at: null,
    };
    this.store.api_keys[keyId] = record;
    const publicRecord = publicApiKey(record);
    this.appendAudit(tenantId, projectId, "api_key.create", { targetId: keyId, apiKeyId: options.authKeyId, after: publicRecord });
    if (options.revealSecret === true) {
      return { ...publicRecord, one_time_secret: syntheticSecret, one_time_secret_displayed: true, secret_value_present: true };
    }
    return publicRecord;
  }

  revokeApiKey(tenantId: string, projectId: string, keyId: string, options: { authKeyId?: string } = {}): JsonRecord {
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const record = this.apiKeyRecord(tenantId, projectId, keyId);
    const before = publicApiKey(record);
    record.status = "revoked";
    record.revoked_at = utcNow();
    const after = publicApiKey(record);
    this.appendAudit(tenantId, projectId, "api_key.revoke", { targetId: keyId, apiKeyId: options.authKeyId, before, after });
    return after;
  }

  listApiKeys(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord[] {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_READ_SCOPE });
    }
    return Object.values(this.store.api_keys)
      .filter((record) => record.tenant_id === tenantId && record.project_id === projectId)
      .map((record) => publicApiKey(record));
  }

  authenticateApiKey(tenantId: string, projectId: string, options: { keyId: string; scope: string; consumeRate?: boolean }): JsonRecord {
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    const requiredScope = normalizeScope(options.scope);
    if (record.status !== "active") {
      throw new ValidationError(`api key is not active: ${options.keyId}`);
    }
    if (!scopeAllows(record.scopes, requiredScope)) {
      throw new ValidationError(`api key ${options.keyId} missing required scope: ${requiredScope}`);
    }
    if (options.consumeRate !== false) this.consumeApiKeyRate(record, requiredScope);
    record.last_used_at = utcNow();
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      authenticated: true,
      required_scope: requiredScope,
      api_key: publicApiKey(record),
      secret_value_present: false,
    };
  }

  verifyApiKeySecret(tenantId: string, projectId: string, options: { keyId: string; secret: string; scope?: string }): JsonRecord {
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    if (record.status !== "active") {
      throw new ValidationError(`api key is not active: ${options.keyId}`);
    }
    if (secretHash(options.secret) !== record.secret_hash_sha256) {
      throw new ValidationError("api key secret verification failed");
    }
    if (options.scope !== undefined) {
      return this.authenticateApiKey(tenantId, projectId, { keyId: options.keyId, scope: options.scope });
    }
    record.last_used_at = utcNow();
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      verified: true,
      api_key: publicApiKey(record),
      secret_value_present: false,
    };
  }

  apiKeyIdForSecret(tenantId: string, projectId: string, secret: string | undefined): string | undefined {
    if (secret === undefined || secret.trim() === "") return undefined;
    const hash = secretHash(secret);
    for (const record of Object.values(this.store.api_keys)) {
      if (record.tenant_id === tenantId && record.project_id === projectId && record.secret_hash_sha256 === hash) {
        return String(record.key_id);
      }
    }
    throw new ValidationError("api key secret verification failed");
  }

  configureApiKeyRateLimit(tenantId: string, projectId: string, options: { keyId: string; operation: string; limit: number; period?: string; authKeyId?: string }): JsonRecord {
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    const limit = Number(options.limit);
    if (!Number.isFinite(limit) || limit <= 0) {
      throw new ValidationError("api key rate limit must be positive");
    }
    const operation = normalizeScope(options.operation);
    const period = options.period ?? "local-window";
    const bucketKey = apiKeyRateKey(tenantId, projectId, options.keyId, operation, period);
    const bucket: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      operation,
      period,
      limit: Math.trunc(limit),
      used: 0,
      remaining: Math.trunc(limit),
      created_at: utcNow(),
    };
    this.store.api_key_rate_limits[bucketKey] = bucket;
    this.appendAudit(tenantId, projectId, "api_key.rate_limit.configure", { targetId: options.keyId, apiKeyId: options.authKeyId, after: { api_key: publicApiKey(record), rate_limit: bucket } });
    return cloneJson(bucket) as JsonRecord;
  }

  apiKeyRateLimitSnapshot(tenantId: string, projectId: string, options: { keyId?: string } = {}): JsonRecord {
    const buckets = Object.values(this.store.api_key_rate_limits)
      .filter((bucket) => bucket.tenant_id === tenantId && bucket.project_id === projectId && (options.keyId === undefined || bucket.key_id === options.keyId));
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId ?? null,
      rate_limits: cloneJson(buckets),
    };
  }

  configureOauthProvider(tenantId: string, projectId: string, options: SaaSOAuthProviderConfigureOptions): SaaSOAuthProviderConfig {
    const project = this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: COMMERCIAL_CONFIG_WRITE_SCOPE, consumeRate: false });
      this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.authKeyId), "oauth.provider.configure");
    }
    const provider = normalizeOauthProvider(options.provider);
    if (options.redirectUris.length === 0) throw new ValidationError("oauth redirect_uris must not be empty");
    if (options.scopes.length === 0) throw new ValidationError("oauth scopes must not be empty");
    for (const uri of options.redirectUris) {
      if (!uri.startsWith("https://") && !uri.startsWith("http://localhost")) throw new ValidationError("oauth redirect_uri must be https or localhost");
    }
    validateSecretRef("client_id_ref", options.clientIdRef);
    validateSecretRef("client_secret_ref", options.clientSecretRef);
    const configId = options.configId ?? newId("oauthcfg");
    const now = utcNow();
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      config_id: configId,
      provider,
      client_id_ref: options.clientIdRef,
      client_secret_ref: options.clientSecretRef,
      redirect_uris: [...options.redirectUris],
      scopes: [...options.scopes],
      enabled: true,
      secret_value_present: false,
      created_at: now,
      updated_at: now,
      configured_by_api_key_id: options.authKeyId ?? null,
    };
    this.store.oauth_provider_configs[configId] = record;
    const publicRecord = publicOauthProviderConfig(record);
    this.appendAudit(tenantId, projectId, "oauth.provider.configure", { targetId: configId, apiKeyId: options.authKeyId, after: publicRecord });
    return publicRecord;
  }

  beginOauthAuthorization(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationBeginOptions): SaaSOAuthAuthorizationBeginResult {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: COMMERCIAL_CONFIG_WRITE_SCOPE, consumeRate: false });
      this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.authKeyId), "oauth.authorization.begin");
    }
    const config = this.oauthProviderConfigRecord(tenantId, projectId, options.providerConfigId);
    if (!(config.redirect_uris as unknown[]).includes(options.redirectUri)) throw new ValidationError("oauth redirect_uri must match provider config");
    const state = options.state ?? newId("oauthstate");
    validateOauthState(state);
    const flowId = newId("oauthflow");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      flow_id: flowId,
      provider: config.provider,
      provider_config_id: options.providerConfigId,
      redirect_uri: options.redirectUri,
      state_hash_sha256: sha256(state),
      code_challenge: pkceS256Challenge(options.codeVerifier),
      code_challenge_method: "S256",
      status: "pending",
      session_id: null,
      failure_reasons: [],
      secret_value_present: false,
      raw_code_present: false,
      raw_state_present: false,
      created_at: utcNow(),
      completed_at: null,
      created_by_api_key_id: options.authKeyId ?? null,
    };
    this.store.oauth_authorization_flows[flowId] = record;
    const publicRecord = publicOauthAuthorizationFlow(record);
    this.appendAudit(tenantId, projectId, "oauth.authorization.begin", { targetId: flowId, apiKeyId: options.authKeyId, after: publicRecord });
    return { ...publicRecord, state };
  }

  completeOauthAuthorization(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationCompleteOptions): SaaSOAuthAuthorizationCompleteResult {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: COMMERCIAL_CONFIG_WRITE_SCOPE, consumeRate: false });
      this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.authKeyId), "oauth.authorization.complete");
    }
    const flow = this.oauthAuthorizationFlowRecord(tenantId, projectId, options.flowId);
    const failures: string[] = [];
    if (flow.status !== "pending") failures.push("oauth_state_replay");
    if (sha256(options.state) !== flow.state_hash_sha256) failures.push("oauth_state_mismatch");
    if (pkceS256Challenge(options.codeVerifier) !== flow.code_challenge) failures.push("pkce_verifier_mismatch");
    if (options.redirectUri !== flow.redirect_uri) failures.push("redirect_uri_mismatch");
    if (options.providerError) failures.push("provider_error");
    if (options.providerCodeRef !== undefined) validateSecretRef("provider_code_ref", options.providerCodeRef);
    const before = publicOauthAuthorizationFlow(flow);
    if (failures.length > 0) {
      if (flow.status === "pending") flow.status = "failed";
      flow.failure_reasons = failures;
      flow.completed_at = utcNow();
      const rejected = publicOauthAuthorizationFlow(flow);
      this.appendAudit(tenantId, projectId, "oauth.authorization.reject", { targetId: options.flowId, apiKeyId: options.authKeyId, before, after: rejected });
      return { ...rejected, accepted: false };
    }
    validatePublicRef("subject_ref", options.subjectRef);
    if (options.accessTokenRef !== undefined) validateSecretRef("access_token_ref", options.accessTokenRef);
    if (options.refreshTokenRef !== undefined) validateSecretRef("refresh_token_ref", options.refreshTokenRef);
    const sessionId = options.sessionId ?? newId("oauthsess");
    const sessionRecord: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      session_id: sessionId,
      provider: flow.provider,
      provider_config_id: flow.provider_config_id,
      subject_ref: options.subjectRef,
      access_token_ref: options.accessTokenRef ?? null,
      refresh_token_ref: options.refreshTokenRef ?? null,
      status: "active",
      secret_value_present: false,
      created_at: utcNow(),
      revoked_at: null,
      created_by_api_key_id: options.authKeyId ?? null,
    };
    this.store.oauth_sessions[sessionId] = sessionRecord;
    flow.status = "completed";
    flow.completed_at = utcNow();
    flow.session_id = sessionId;
    flow.provider_code_ref_sha256 = options.providerCodeRef === undefined ? null : sha256(options.providerCodeRef);
    delete flow.provider_code_ref;
    flow.failure_reasons = [];
    const completed = publicOauthAuthorizationFlow(flow);
    const session = publicOauthSession(sessionRecord);
    this.appendAudit(tenantId, projectId, "oauth.authorization.complete", { targetId: options.flowId, apiKeyId: options.authKeyId, before, after: completed });
    return { ...completed, accepted: true, session };
  }

  sdkSubmitRun(tenantId: string, projectId: string, options: { datasetId: string; agentRef: string; runId?: string; metadata?: JsonRecord; apiKeyId?: string; idempotencyKey?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: "sdk:submit", consumeRate: false });
    }
    const requestFingerprint = requestFingerprintSha256({ dataset_id: options.datasetId, agent_ref: options.agentRef, run_id: options.runId ?? null, metadata: options.metadata ?? {}, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "sdk.submit", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), "sdk:submit");
    this.cloud.quota.check(tenantId, projectId, "sdk.submit");
    const run = this.cloud.createQueuedRun(tenantId, projectId, {
      datasetId: options.datasetId,
      runId: options.runId,
      runnerId: "sdk-submit",
      metadata: { submitted_by: "sdk", agent_ref: options.agentRef, ...(options.metadata ?? {}) },
    });
    this.consumeUsage(tenantId, projectId, "sdk.submit", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId: run.run_id });
    const submission: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      submission_id: newId("sdksub"),
      tenant_id: tenantId,
      project_id: projectId,
      dataset_id: options.datasetId,
      run_id: run.run_id,
      agent_ref: options.agentRef,
      status: "accepted",
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.store.sdk_submissions[String(submission.submission_id)] = submission;
    const response = cloneJson({ submission, run }) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "sdk.submit", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "sdk.submit", { targetId: run.run_id, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { run_id: run.run_id, submission_id: submission.submission_id } });
    return response;
  }

  uploadRunResult(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: { uploadId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: RUN_UPLOAD_SCOPE, consumeRate: false });
    }
    const payload = jsonRecord(result);
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, result: payload, upload_id: options.uploadId ?? null, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "run.upload", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), RUN_UPLOAD_SCOPE);
    const run = this.cloud.getRun(tenantId, projectId, runId);
    this.consumeUsage(tenantId, projectId, "run.upload", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const digest = sha256(JSON.stringify(sortJson(payload)));
    const uploadId = options.uploadId ?? newId("upload");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      upload_id: uploadId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: run.run_id,
      payload_sha256: digest,
      payload_keys: Object.keys(payload).sort(),
      raw_payload_included: false,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      status: "uploaded",
      created_at: utcNow(),
    };
    this.store.uploads[uploadId] = record;
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "run.upload", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "run.upload", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { upload_id: uploadId, payload_sha256: digest } });
    return response;
  }

  ingestTrace(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: TRACE_INGEST_SCOPE, consumeRate: false });
    }
    const normalized = observations.map((item) => jsonRecord(item));
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, observations: normalized, batch_id: options.batchId ?? null, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "trace.ingest", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), TRACE_INGEST_SCOPE);
    this.cloud.getRun(tenantId, projectId, runId);
    if (observations.length === 0) {
      throw new ValidationError("trace ingestion requires at least one observation");
    }
    this.consumeUsage(tenantId, projectId, "trace.ingest", { units: observations.length, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const batchSha = sha256(JSON.stringify(sortJson(normalized)));
    const appended = normalized.map((item) => this.cloud.appendObservation(tenantId, projectId, runId, item));
    const batchId = options.batchId ?? newId("tracebatch");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      batch_id: batchId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      observation_count: appended.length,
      observation_ids: appended.map((item) => item.observation_id),
      batch_sha256: batchSha,
      raw_payload_included: false,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      status: "ingested",
      created_at: utcNow(),
    };
    this.store.trace_batches[batchId] = record;
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "trace.ingest", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "trace.ingest", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { batch_id: batchId, batch_sha256: batchSha } });
    return response;
  }

  lifecycleSnapshot(tenantId: string, projectId: string, runId: string): JsonRecord {
    const tenant = this.cloud.getTenant(tenantId);
    const project = this.cloud.getProject(tenantId, projectId);
    const run = this.cloud.getRun(tenantId, projectId, runId);
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenant.tenant_id,
      project_id: project.project_id,
      run_id: run.run_id,
      tenant_status: "active",
      project_status: "active",
      run_status: run.status,
      run_result_status: run.result_status,
      status_history: run.status_history,
      quota: this.cloud.quotaSnapshot(tenantId, projectId),
      api_keys: this.listApiKeys(tenantId, projectId),
      uploads: Object.values(this.store.uploads).filter((item) => item.run_id === runId),
      trace_batches: Object.values(this.store.trace_batches).filter((item) => item.run_id === runId),
      usage_ledger: Object.values(this.store.usage_ledger).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (item.run_id === undefined || item.run_id === null || item.run_id === runId)),
      audit_log: Object.values(this.store.audit_log).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (item.target_id === undefined || item.target_id === null || item.target_id === runId)),
    };
  }

  usageSnapshot(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId === undefined) throw new ValidationError("usage snapshot requires authKeyId with usage:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: USAGE_READ_SCOPE });
    const events = Object.values(this.store.usage_ledger).filter((item) => item.tenant_id === tenantId && item.project_id === projectId);
    const totals: Record<string, number> = {};
    for (const event of events) {
      const op = String(event.operation);
      totals[op] = (totals[op] ?? 0) + Number(event.units ?? 0);
    }
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, tenant_id: tenantId, project_id: projectId, events, totals, quota: this.cloud.quotaSnapshot(tenantId, projectId) };
  }

  billingCheckoutPlan(tenantId: string, projectId: string, options: JsonRecord & { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: BILLING_WRITE_SCOPE });
    return buildCheckoutSessionPlan({ ...options, tenantId, projectId } as Parameters<typeof buildCheckoutSessionPlan>[0]);
  }

  billingPortalPlan(tenantId: string, projectId: string, options: JsonRecord & { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: BILLING_WRITE_SCOPE });
    return buildBillingPortalPlan({ ...options, tenantId, projectId });
  }

  billingWebhookIngest(tenantId: string, projectId: string, options: JsonRecord & { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: BILLING_WEBHOOK_SCOPE });
    const envelopeResult = verifyBillingWebhookEnvelope({ ...options, tenantId, projectId, signatureHeaderPresent: Boolean(options.signatureHeaderPresent ?? options.signature_header_present) } as Parameters<typeof verifyBillingWebhookEnvelope>[0]);
    return this.billingLedger.ingestProviderWebhook({
      envelope: envelopeResult,
      customerRef: clientString(options, "customerRef", "customer_ref"),
      amountMinor: Number(options.amountMinor ?? options.amount_minor ?? 0),
      currency: clientString(options, "currency") || "usd",
      invoiceRef: clientString(options, "invoiceRef", "invoice_ref"),
      usageUnits: Number(options.usageUnits ?? options.usage_units ?? 0),
      metadata: isRecord(options.metadata) ? options.metadata : {},
    });
  }

  billingLedgerSnapshot(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: BILLING_READ_SCOPE });
    return this.billingLedger.publicLedger({ tenantId, projectId });
  }

  createArtifactManifest(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId === undefined) throw new ValidationError("artifact manifest upload requires apiKeyId with artifact:upload scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: ARTIFACT_MANIFEST_SCOPE, consumeRate: false });
    const manifestCopy = cloneJson(manifest) as JsonRecord;
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, manifest: manifestCopy, artifact_id: options.artifactId ?? null, api_key_id: options.apiKeyId });
    const cached = this.idempotencyLookup(tenantId, projectId, "artifact.manifest", options.idempotencyKey, requestFingerprint);
    if (cached !== null) return { ...cached, idempotent_replay: true };
    this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), ARTIFACT_MANIFEST_SCOPE);
    this.cloud.getRun(tenantId, projectId, runId);
    const usage = this.consumeUsage(tenantId, projectId, "artifact.manifest", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const artifactId = options.artifactId ?? newId("artifact");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      artifact_id: artifactId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      manifest_schema_version: String(manifestCopy.schema_version ?? "ashr.clone.artifact_manifest.v1"),
      manifest_keys: Object.keys(manifestCopy).sort(),
      manifest_sha256: sha256(JSON.stringify(sortJson(manifestCopy))),
      raw_manifest_included: false,
      api_key_id: options.apiKeyId ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
      usage_event_id: usage.usage_event_id,
    };
    this.store.artifact_manifests[artifactId] = record;
    this.appendAudit(tenantId, projectId, "artifact.manifest", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: record });
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "artifact.manifest", options.idempotencyKey, requestFingerprint, response);
    return response;
  }

  listArtifactManifests(tenantId: string, projectId: string, runId?: string, options: { authKeyId?: string } = {}): JsonRecord[] {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId === undefined) throw new ValidationError("artifact manifest read requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    return Object.values(this.store.artifact_manifests).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (runId === undefined || item.run_id === runId)).map((item) => cloneJson(item) as JsonRecord);
  }

  evaluateReleaseGate(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): JsonRecord {
    this.cloud.getRun(tenantId, projectId, runId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const lifecycle = this.lifecycleSnapshot(tenantId, projectId, runId);
    const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
    const traceBatches = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
    const observationCount = traceBatches.reduce((total, batch) => total + Number(isRecord(batch) ? batch.observation_count ?? 0 : 0), 0);
    const uploadStatuses = uploads.map((item) => String(isRecord(item) ? item.status ?? "" : "")).filter(Boolean).sort();
    const traceCompleteness = uploads.length === 0 ? 0 : Math.min(1, observationCount / Math.max(1, uploads.length));
    const hasUploadedResult = uploadStatuses.includes("uploaded");
    const score = Math.min(1, Number((0.35 + Math.min(0.35, observationCount * 0.12) + (hasUploadedResult ? 0.3 : 0)).toFixed(4)));
    const minScore = options.minScore ?? 0.72;
    const requiredTraceCompleteness = options.requiredTraceCompleteness ?? 0.95;
    const blockers = [
      score >= minScore ? null : "score_below_threshold",
      traceCompleteness >= requiredTraceCompleteness ? null : "trace_completeness_below_threshold",
      hasUploadedResult ? null : "missing_run_upload",
    ].filter((item): item is string => item !== null);
    const result: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      evaluator: options.evaluator ?? "local-deterministic-release-gate",
      decision: blockers.length === 0 ? "pass" : "block",
      score,
      min_score: minScore,
      trace_completeness: Number(traceCompleteness.toFixed(4)),
      required_trace_completeness: requiredTraceCompleteness,
      upload_count: uploads.length,
      trace_batch_count: traceBatches.length,
      observation_count: observationCount,
      blockers,
      local_only: true,
      ashr_api_used: false,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.appendAudit(tenantId, projectId, "release_gate.evaluate", { targetId: runId, apiKeyId: options.authKeyId, requestId: options.requestId, after: result });
    return result;
  }

  auditSnapshot(tenantId: string, projectId: string, options: { runId?: string; actionPrefix?: string; authKeyId?: string; limit?: number } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const limit = Math.max(1, Math.min(500, Math.trunc(options.limit ?? 100)));
    const ledgerEvents = Object.values(this.store.audit_log)
      .filter((item) => item.tenant_id === tenantId && item.project_id === projectId) as JsonRecord[];
    const chain = verifyAuditHashChain(ledgerEvents);
    const events = auditEventsInChainOrder(ledgerEvents
      .filter((item) => options.runId === undefined || item.target_id === options.runId || item.target_id === null)
      .filter((item) => options.actionPrefix === undefined || String(item.action).startsWith(options.actionPrefix)))
      .slice(-limit)
      .map((item) => cloneJson(item) as JsonRecord);
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: options.runId ?? null,
      action_prefix: options.actionPrefix ?? null,
      limit,
      event_count: events.length,
      events,
      chain,
      raw_payload_included: false,
      secret_value_present: false,
    };
  }

  verifyAuditChain(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): JsonRecord {
    if (options.authKeyId === undefined) throw new ValidationError("audit-chain verification requires authKeyId with audit:read scope");
    const snapshot = this.auditSnapshot(tenantId, projectId, { authKeyId: options.authKeyId, limit: 500 });
    const usage = this.consumeUsage(tenantId, projectId, "audit_chain.verify", { apiKeyId: options.authKeyId, requestId: options.requestId });
    const response: JsonRecord = {
      schema_version: "ashr.clone.audit_chain_verification.v1",
      tenant_id: tenantId,
      project_id: projectId,
      ...cloneJson(snapshot.chain) as JsonRecord,
      usage_event_id: usage.usage_event_id,
      raw_payload_included: false,
      secret_value_present: false,
    };
    this.appendAudit(tenantId, projectId, "audit_chain.verify", { apiKeyId: options.authKeyId, requestId: options.requestId, after: { verified: response.verified, event_count: response.event_count, usage_event_id: usage.usage_event_id } });
    return response;
  }

  buildReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { releaseGate?: JsonRecord; authKeyId?: string } = {}): JsonRecord {
    const lifecycle = this.lifecycleSnapshot(tenantId, projectId, runId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const releaseGate = options.releaseGate ?? this.evaluateReleaseGate(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    if (options.authKeyId === undefined) throw new ValidationError("release evidence read requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    const artifacts = this.listArtifactManifests(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    const usage = this.usageSnapshot(tenantId, projectId, { authKeyId: options.authKeyId });
    const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
    const traces = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
    const audit = this.auditSnapshot(tenantId, projectId, { runId, limit: 200, authKeyId: options.authKeyId });
    const payload = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      packet_schema_version: "ashr.clone.release_evidence_packet.v1",
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      generated_at: utcNow(),
      local_only: true,
      ashr_api_used: false,
      lifecycle: {
        run_status: lifecycle.run_status,
        run_result_status: lifecycle.run_result_status,
        status_history_count: Array.isArray(lifecycle.status_history) ? lifecycle.status_history.length : 0,
      },
      release_gate: cloneJson(releaseGate),
      counts: {
        uploads: uploads.length,
        trace_batches: traces.length,
        observations: traces.reduce((total, batch) => total + Number(isRecord(batch) ? batch.observation_count ?? 0 : 0), 0),
        artifacts: artifacts.length,
        audit_events: audit.event_count,
        usage_events: Array.isArray(usage.events) ? usage.events.length : 0,
      },
      hashes: {
        uploads_sha256: sha256(JSON.stringify(sortJson(uploads))),
        traces_sha256: sha256(JSON.stringify(sortJson(traces))),
        artifacts_sha256: sha256(JSON.stringify(sortJson(artifacts))),
        audit_sha256: sha256(JSON.stringify(sortJson(audit.events))),
      },
      audit_chain: audit.chain,
      usage_totals: usage.totals,
      redaction: { raw_payload_included: false, secret_value_present: false, secret_hash_included: false },
    };
    return { ...payload, integrity: { packet_sha256: sha256(JSON.stringify(sortJson(payload))) } };
  }

  verifyReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): JsonRecord {
    if (options.authKeyId === undefined) throw new ValidationError("release-evidence verification requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    const packet = options.packet ?? this.buildReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    const verification = verifyReleaseEvidencePacket(packet);
    const failures = Array.isArray(verification.failures) ? [...verification.failures] : [];
    if (String(packet.tenant_id ?? "") !== tenantId) failures.push({ reason: "tenant_id_mismatch", expected: tenantId, actual: packet.tenant_id ?? null });
    if (String(packet.project_id ?? "") !== projectId) failures.push({ reason: "project_id_mismatch", expected: projectId, actual: packet.project_id ?? null });
    if (String(packet.run_id ?? "") !== runId) failures.push({ reason: "run_id_mismatch", expected: runId, actual: packet.run_id ?? null });
    const bindings = releasePacketBindings(this, tenantId, projectId, runId, options.authKeyId);
    failures.push(...verifyReleasePacketBindings(packet, bindings));
    const usage = this.consumeUsage(tenantId, projectId, "release_evidence.verify", { apiKeyId: options.authKeyId, requestId: options.requestId, runId });
    const response: JsonRecord = {
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      ...verification,
      verified: failures.length === 0,
      failures,
      bindings,
      usage_event_id: usage.usage_event_id,
      source: options.packet === undefined ? "current_snapshot" : "submitted_packet",
      raw_payload_included: false,
      secret_value_present: false,
    };
    this.appendAudit(tenantId, projectId, "release_evidence.verify", { targetId: runId, apiKeyId: options.authKeyId, requestId: options.requestId, after: { verified: response.verified, packet_sha256: response.packet_sha256, actual_packet_sha256: response.actual_packet_sha256, usage_event_id: usage.usage_event_id } });
    return {
      ...response,
    };
  }

  enqueueWorkerJob(tenantId: string, projectId: string, options: { jobType: string; targetId?: string; payload?: JsonRecord; jobId?: string; priority?: number; maxAttempts?: number; apiKeyId?: string; idempotencyKey?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: WORKER_JOB_WRITE_SCOPE, consumeRate: false });
    this.cloud.getProject(tenantId, projectId);
    const payload = sortJson(options.payload ?? {}) as JsonRecord;
    const fingerprint = requestFingerprintSha256({ tenant_id: tenantId, project_id: projectId, operation: "worker.job.enqueue", job_type: options.jobType, target_id: options.targetId ?? null, payload, job_id: options.jobId ?? null, priority: options.priority ?? 100, max_attempts: options.maxAttempts ?? 3, api_key_id: options.apiKeyId ?? null });
    const replay = this.idempotencyLookup(tenantId, projectId, "worker.job.enqueue", options.idempotencyKey, fingerprint);
    if (replay !== null) return replay;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), "worker:write");
    this.cloud.quota.check(tenantId, projectId, "worker.job.enqueue");
    const jobId = options.jobId ?? newId("job");
    if (this.store.worker_jobs[jobId] !== undefined) throw new ValidationError(`worker job already exists: ${jobId}`);
    const maxAttempts = positiveInt(options.maxAttempts ?? 3, "max_attempts");
    const now = utcNow();
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION,
      job_id: jobId,
      tenant_id: tenantId,
      project_id: projectId,
      job_type: String(options.jobType),
      target_id: options.targetId ?? null,
      payload_sha256: sha256(JSON.stringify(payload)),
      raw_payload_included: false,
      status: "queued",
      priority: Number(options.priority ?? 100),
      attempts: 0,
      max_attempts: maxAttempts,
      lease_owner_id: null,
      lease_expires_at: null,
      available_at: now,
      last_error: null,
      result_sha256: null,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: now,
      updated_at: now,
    };
    this.store.worker_jobs[jobId] = record;
    this.consumeUsage(tenantId, projectId, "worker.job.enqueue", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId: options.targetId });
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "worker.job.enqueue", options.idempotencyKey, fingerprint, response);
    this.appendAudit(tenantId, projectId, "worker.job.enqueue", { targetId: jobId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { job_id: jobId, job_type: record.job_type, target_id: options.targetId ?? null } });
    return response;
  }

  leaseWorkerJob(tenantId: string, projectId: string, options: { leaseOwnerId: string; leaseSeconds?: number; jobType?: string; apiKeyId?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: WORKER_JOB_WRITE_SCOPE, consumeRate: false });
    if (options.leaseOwnerId.trim() === "") throw new ValidationError("lease_owner_id is required");
    this.cloud.getProject(tenantId, projectId);
    const now = utcNow();
    const candidates = Object.values(this.store.worker_jobs).filter((job) => job.tenant_id === tenantId && job.project_id === projectId && ["queued", "leased", "retrying"].includes(String(job.status)) && (options.jobType === undefined || job.job_type === options.jobType) && jobAvailableForLease(job, now));
    candidates.sort((a, b) => Number(a.priority ?? 100) - Number(b.priority ?? 100) || String(a.available_at ?? "").localeCompare(String(b.available_at ?? "")) || String(a.created_at ?? "").localeCompare(String(b.created_at ?? "")) || String(a.job_id ?? "").localeCompare(String(b.job_id ?? "")));
    if (candidates.length === 0) return { schema_version: CONTROL_PLANE_SCHEMA_VERSION, status: "empty", tenant_id: tenantId, project_id: projectId, job: null, leased: false, created_at: now };
    const job = candidates[0];
    const before = cloneJson(job) as JsonRecord;
    job.status = "leased";
    job.attempts = Number(job.attempts ?? 0) + 1;
    job.lease_owner_id = options.leaseOwnerId;
    job.lease_expires_at = leaseExpiresAt(now, options.leaseSeconds ?? 300);
    job.updated_at = now;
    this.consumeUsage(tenantId, projectId, "worker.job.lease", { apiKeyId: options.apiKeyId, requestId: options.requestId, runId: typeof job.target_id === "string" ? job.target_id : undefined });
    this.appendAudit(tenantId, projectId, "worker.job.lease", { targetId: String(job.job_id), apiKeyId: options.apiKeyId, requestId: options.requestId, before, after: { job_id: job.job_id, attempts: job.attempts, lease_owner_id: options.leaseOwnerId, lease_expires_at: job.lease_expires_at } });
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION, status: "leased", tenant_id: tenantId, project_id: projectId, leased: true, job: cloneJson(job) as JsonRecord };
  }

  completeWorkerJob(tenantId: string, projectId: string, jobId: string, result: JsonRecord = {}, options: { leaseOwnerId: string; apiKeyId?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: WORKER_JOB_WRITE_SCOPE, consumeRate: false });
    const job = this.workerJobRecord(tenantId, projectId, jobId);
    requireWorkerJobLease(job, options.leaseOwnerId);
    const before = cloneJson(job) as JsonRecord;
    const now = utcNow();
    job.status = "completed";
    job.lease_owner_id = null;
    job.lease_expires_at = null;
    job.result_sha256 = sha256(JSON.stringify(sortJson(result)));
    job.updated_at = now;
    job.completed_at = now;
    this.consumeUsage(tenantId, projectId, "worker.job.complete", { apiKeyId: options.apiKeyId, requestId: options.requestId, runId: typeof job.target_id === "string" ? job.target_id : undefined });
    this.appendAudit(tenantId, projectId, "worker.job.complete", { targetId: jobId, apiKeyId: options.apiKeyId, requestId: options.requestId, before, after: { job_id: jobId, status: job.status, result_sha256: job.result_sha256 } });
    return cloneJson(job) as JsonRecord;
  }

  heartbeatWorkerJob(tenantId: string, projectId: string, jobId: string, options: { leaseOwnerId: string; leaseSeconds?: number; apiKeyId?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: WORKER_JOB_WRITE_SCOPE, consumeRate: false });
    const job = this.workerJobRecord(tenantId, projectId, jobId);
    requireWorkerJobLease(job, options.leaseOwnerId);
    const before = cloneJson(job) as JsonRecord;
    const now = utcNow();
    job.lease_expires_at = leaseExpiresAt(now, options.leaseSeconds ?? 300);
    job.updated_at = now;
    this.appendAudit(tenantId, projectId, "worker.job.heartbeat", { targetId: jobId, apiKeyId: options.apiKeyId, requestId: options.requestId, before, after: { job_id: jobId, lease_owner_id: options.leaseOwnerId, lease_expires_at: job.lease_expires_at } });
    return cloneJson(job) as JsonRecord;
  }

  failWorkerJob(tenantId: string, projectId: string, jobId: string, error: JsonRecord = {}, options: { leaseOwnerId: string; retryAfterSeconds?: number; apiKeyId?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: WORKER_JOB_WRITE_SCOPE, consumeRate: false });
    const job = this.workerJobRecord(tenantId, projectId, jobId);
    requireWorkerJobLease(job, options.leaseOwnerId);
    const before = cloneJson(job) as JsonRecord;
    const now = utcNow();
    const attempts = Number(job.attempts ?? 0);
    const maxAttempts = Number(job.max_attempts ?? 1);
    const normalizedError = sortJson(error) as JsonRecord;
    job.last_error = { sha256: sha256(JSON.stringify(normalizedError)), type: String(normalizedError.type ?? "worker_error"), message: String(normalizedError.message ?? "redacted"), raw_payload_included: false, failed_at: now };
    job.lease_owner_id = null;
    job.lease_expires_at = null;
    if (attempts >= maxAttempts) {
      job.status = "dead_lettered";
      job.dead_lettered_at = now;
      job.available_at = null;
    } else {
      job.status = "retrying";
      const retryAfter = options.retryAfterSeconds ?? Math.min(3600, 2 ** Math.max(0, attempts - 1));
      job.available_at = retryAfter === 0 ? now : leaseExpiresAt(now, retryAfter);
    }
    job.updated_at = now;
    this.consumeUsage(tenantId, projectId, "worker.job.fail", { apiKeyId: options.apiKeyId, requestId: options.requestId, runId: typeof job.target_id === "string" ? job.target_id : undefined });
    this.appendAudit(tenantId, projectId, "worker.job.fail", { targetId: jobId, apiKeyId: options.apiKeyId, requestId: options.requestId, before, after: { job_id: jobId, status: job.status, attempts, last_error_sha256: (job.last_error as JsonRecord).sha256 } });
    return cloneJson(job) as JsonRecord;
  }

  listWorkerJobs(tenantId: string, projectId: string, options: { status?: string; jobType?: string; limit?: number; authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: WORKER_JOB_READ_SCOPE });
    let jobs = Object.values(this.store.worker_jobs).filter((job) => job.tenant_id === tenantId && job.project_id === projectId);
    if (options.status !== undefined) jobs = jobs.filter((job) => job.status === options.status);
    if (options.jobType !== undefined) jobs = jobs.filter((job) => job.job_type === options.jobType);
    jobs = jobs.map((job) => cloneJson(job) as JsonRecord).sort((a, b) => Number(a.priority ?? 100) - Number(b.priority ?? 100) || String(a.created_at ?? "").localeCompare(String(b.created_at ?? "")) || String(a.job_id ?? "").localeCompare(String(b.job_id ?? "")));
    const totalCount = jobs.length;
    const requestedLimit = options.limit === undefined ? undefined : positiveInt(options.limit, "limit");
    if (requestedLimit !== undefined) jobs = jobs.slice(0, requestedLimit);
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      filters: { status: options.status ?? null, job_type: options.jobType ?? null, limit: requestedLimit ?? null },
      jobs,
      count: jobs.length,
      returned_count: jobs.length,
      total_count: totalCount,
      has_more: requestedLimit !== undefined && totalCount > jobs.length,
      next_cursor: null,
    };
  }

  snapshotState(): SaaSControlPlaneState {
    const payload = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      state_schema_version: 2,
      cloud: this.cloud.snapshotState() as JsonRecord,
      metadata: { local_only: true as const, ashr_api_used: false as const },
      state_metadata: { writer: "packages/ts/ashr-clone/saas", updated_at: utcNow() },
      control_plane: cloneJson(this.store),
      billing_ledger: this.billingLedgerState(),
    };
    return { ...payload, integrity: { payload_sha256: sha256(JSON.stringify(sortJson(payload))) } };
  }

  async writeState(outputPath: string): Promise<string> {
    assertPublicControlPlanePath(outputPath);
    const fs = await import("node:fs/promises");
    const pathModule = await import("node:path");
    const resolved = pathModule.resolve(outputPath);
    await fs.mkdir(pathModule.dirname(resolved), { recursive: true });
    const tmp = `${resolved}.tmp`;
    await fs.writeFile(tmp, `${JSON.stringify(sortJson(this.snapshotState()), null, 2)}\n`, "utf8");
    await fs.rename(tmp, resolved);
    return resolved;
  }

  static fromState(payload: unknown): SaaSControlPlaneService {
    if (!isRecord(payload)) {
      throw new ValidationError("control-plane state payload must be an object");
    }
    const version = Number(payload.state_schema_version ?? 1);
    if (![1, 2].includes(version)) {
      throw new ValidationError(`unsupported control-plane state schema version: ${version}`);
    }
    const control = isRecord(payload.control_plane) ? payload.control_plane : {};
    const service = new SaaSControlPlaneService({
      cloud: CloudApiService.fromState(payload.cloud),
      store: {
        api_keys: stateBucket(control, "api_keys"),
        api_key_rate_limits: stateBucket(control, "api_key_rate_limits"),
        uploads: stateBucket(control, "uploads"),
        trace_batches: stateBucket(control, "trace_batches"),
        sdk_submissions: stateBucket(control, "sdk_submissions"),
        audit_log: stateBucket(control, "audit_log"),
        usage_ledger: stateBucket(control, "usage_ledger"),
        idempotency_keys: stateBucket(control, "idempotency_keys"),
        artifact_manifests: stateBucket(control, "artifact_manifests"),
        worker_jobs: stateBucket(control, "worker_jobs"),
        oauth_provider_configs: stateBucket(control, "oauth_provider_configs"),
        oauth_authorization_flows: stateBucket(control, "oauth_authorization_flows"),
        oauth_sessions: stateBucket(control, "oauth_sessions"),
      },
    });
    if (isRecord(payload.billing_ledger)) service.restoreBillingLedgerState(payload.billing_ledger);
    return service;
  }

  static async fromStateFile(inputPath: string): Promise<SaaSControlPlaneService> {
    assertPublicControlPlanePath(inputPath);
    const fs = await import("node:fs/promises");
    return SaaSControlPlaneService.fromState(JSON.parse(await fs.readFile(inputPath, "utf8")) as unknown);
  }

  private apiKeyRecord(tenantId: string, projectId: string, keyId: string): JsonRecord {
    const record = this.store.api_keys[keyId];
    if (record === undefined || record.tenant_id !== tenantId || record.project_id !== projectId) {
      throw new NotFoundError("api key not found for project");
    }
    return record;
  }

  private oauthProviderConfigRecord(tenantId: string, projectId: string, configId: string): JsonRecord {
    const record = this.store.oauth_provider_configs[configId];
    if (record === undefined || record.tenant_id !== tenantId || record.project_id !== projectId) throw new NotFoundError("oauth provider config not found for project");
    return record;
  }

  private oauthAuthorizationFlowRecord(tenantId: string, projectId: string, flowId: string): JsonRecord {
    const record = this.store.oauth_authorization_flows[flowId];
    if (record === undefined || record.tenant_id !== tenantId || record.project_id !== projectId) throw new NotFoundError("oauth authorization flow not found for project");
    return record;
  }

  private workerJobRecord(tenantId: string, projectId: string, jobId: string): JsonRecord {
    const job = this.store.worker_jobs[jobId];
    if (job === undefined || job.tenant_id !== tenantId || job.project_id !== projectId) throw new NotFoundError("worker job not found for project");
    if (job.status === "leased" && leaseExpired(job.lease_expires_at)) {
      job.status = "retrying";
      job.lease_owner_id = null;
      job.lease_expires_at = null;
      job.available_at = utcNow();
      job.updated_at = job.available_at;
    }
    return job;
  }

  private consumeUsage(tenantId: string, projectId: string, operation: string, options: { units?: number; apiKeyId?: string; idempotencyKey?: string; requestId?: string; runId?: string } = {}): JsonRecord {
    const units = options.units ?? 1;
    this.cloud.quota.consume(tenantId, projectId, operation, units);
    const usageEventId = newId("usage");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      usage_event_id: usageEventId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: options.runId ?? null,
      api_key_id: options.apiKeyId ?? null,
      operation,
      units,
      source: "local_control_plane",
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.store.usage_ledger[usageEventId] = record;
    return cloneJson(record) as JsonRecord;
  }

  private appendAudit(tenantId: string, projectId: string, action: string, options: { targetId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string; before?: JsonRecord; after?: JsonRecord } = {}): JsonRecord {
    const auditEventId = newId("audit");
    const before = options.before ?? {};
    const after = options.after ?? {};
    const previousEvent = auditChainTail(Object.values(this.store.audit_log), tenantId, projectId);
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      audit_event_id: auditEventId,
      tenant_id: tenantId,
      project_id: projectId,
      chain_position: previousEvent === null ? 0 : Number(previousEvent.chain_position ?? -1) + 1,
      previous_audit_event_id: previousEvent?.audit_event_id ?? null,
      previous_audit_event_sha256: previousEvent?.audit_event_sha256 ?? null,
      api_key_id: options.apiKeyId ?? null,
      action,
      target_id: options.targetId ?? null,
      before_sha256: Object.keys(before).length > 0 ? sha256(JSON.stringify(sortJson(before))) : null,
      after_sha256: Object.keys(after).length > 0 ? sha256(JSON.stringify(sortJson(after))) : null,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    record.audit_event_sha256 = auditEventHash(record);
    this.store.audit_log[auditEventId] = record;
    return cloneJson(record) as JsonRecord;
  }

  private consumeApiKeyRate(record: JsonRecord, operation: string): void {
    const keyId = String(record.key_id);
    const tenantId = String(record.tenant_id);
    const projectId = String(record.project_id);
    const candidates = Object.values(this.store.api_key_rate_limits)
      .filter((bucket) => bucket.tenant_id === tenantId && bucket.project_id === projectId && bucket.key_id === keyId && (bucket.operation === operation || bucket.operation === "*"));
    for (const bucket of candidates) {
      const used = Number(bucket.used ?? 0);
      const limit = Number(bucket.limit ?? 0);
      if (used + 1 > limit) {
        throw new ValidationError(`api key rate limit exceeded for ${keyId}: ${operation}`);
      }
    }
    for (const bucket of candidates) {
      bucket.used = Number(bucket.used ?? 0) + 1;
      bucket.remaining = Math.max(0, Number(bucket.limit ?? 0) - Number(bucket.used ?? 0));
      bucket.last_used_at = utcNow();
    }
  }

  private idempotencyLookup(tenantId: string, projectId: string, operation: string, idempotencyKey: string | undefined, requestFingerprintSha256: string): JsonRecord | null {
    if (idempotencyKey === undefined) return null;
    const record = this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)];
    if (record === undefined || !isRecord(record.response)) return null;
    if (record.request_fingerprint_sha256 !== requestFingerprintSha256) {
      throw new ValidationError(`idempotency key conflict for ${operation}: request fingerprint mismatch`);
    }
    return { ...cloneJson(record.response), idempotent_replay: true } as JsonRecord;
  }

  private idempotencyStore(tenantId: string, projectId: string, operation: string, idempotencyKey: string | undefined, requestFingerprintSha256: string, response: JsonRecord): void {
    if (idempotencyKey === undefined) return;
    this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)] = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      operation,
      idempotency_key: idempotencyKey,
      request_fingerprint_sha256: requestFingerprintSha256,
      response: cloneJson(response),
      created_at: utcNow(),
    };
  }
}

export class SaaSControlPlaneRouter {
  readonly service: SaaSControlPlaneService;

  constructor(service = new SaaSControlPlaneService()) {
    this.service = service;
  }

  handle(method: string, path: string, body: JsonRecord = {}, options: { headers?: Record<string, string | string[] | undefined> } = {}): SaaSRouterResponse {
    const upperMethod = method.toUpperCase();
    const parts = path.split("/").filter(Boolean);
    try {
      if (upperMethod === "GET" && (parts.join("/") === "healthz" || parts.join("/") === "v1/healthz")) {
        return { status_code: 200, body: saasHealthz() };
      }
      if (upperMethod === "GET" && (parts.join("/") === "openapi.json" || parts.join("/") === "openapi" || parts.join("/") === "healthz/openapi" || parts.join("/") === "v1/openapi" || parts.join("/") === "v1/openapi.json")) {
        return { status_code: 200, body: exportSaaSOpenApiSpec() };
      }
      if (upperMethod === "POST" && parts.join("/") === "v1/bootstrap") {
        return { status_code: 201, body: this.service.bootstrapProject({ tenantName: String(body.tenant_name ?? body.tenantName ?? ""), projectName: String(body.project_name ?? body.projectName ?? ""), tenantId: optionalString(body.tenant_id), projectId: optionalString(body.project_id) }) };
      }
      if (parts.length >= 4 && parts[0] === "v1" && parts[1] === "projects") {
        const projectId = parts[2];
        const tenantId = String(body.tenant_id ?? body.organization_id ?? body.tenant ?? "");
        if (!tenantId) throw new ValidationError("tenant_id is required");
        const explicitAuthKeyId = optionalString(body.auth_key_id ?? body.api_key_id);
        const bearerSecret = bearerSecretFromHeaders(options.headers);
        const authKeyId = explicitAuthKeyId ?? this.service.apiKeyIdForSecret(tenantId, projectId, bearerSecret);
        if (upperMethod === "POST" && parts.length === 4 && parts[3] === "api-keys") {
          return { status_code: 201, body: this.service.createApiKey(tenantId, projectId, { name: String(body.name ?? "API key"), scopes: arrayOfStrings(body.scopes), keyId: optionalString(body.key_id), authKeyId, revealSecret: Boolean(body.reveal_secret) }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "api-keys") {
          return { status_code: 200, body: { api_keys: this.service.listApiKeys(tenantId, projectId, { authKeyId }) } };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "authenticate") {
          return { status_code: 200, body: this.service.authenticateApiKey(tenantId, projectId, { keyId: parts[4], scope: String(body.scope ?? "") }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "verify") {
          return { status_code: 200, body: this.service.verifyApiKeySecret(tenantId, projectId, { keyId: parts[4], secret: String(body.secret ?? ""), scope: optionalString(body.scope) }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "rate-limit") {
          return { status_code: 200, body: this.service.configureApiKeyRateLimit(tenantId, projectId, { keyId: parts[4], operation: String(body.operation ?? "*"), limit: Number(body.limit ?? 0), period: optionalString(body.period), authKeyId }) };
        }
        if (upperMethod === "GET" && parts.length === 5 && parts[3] === "api-keys" && parts[4] === "rate-limits") {
          return { status_code: 200, body: this.service.apiKeyRateLimitSnapshot(tenantId, projectId, { keyId: optionalString(body.key_id) }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "revoke") {
          return { status_code: 200, body: this.service.revokeApiKey(tenantId, projectId, parts[4], { authKeyId }) };
        }
        if (upperMethod === "POST" && parts.length === 4 && parts[3] === "sdk-submit") {
          return { status_code: 202, body: this.service.sdkSubmitRun(tenantId, projectId, { datasetId: String(body.dataset_id ?? ""), agentRef: String(body.agent_ref ?? ""), runId: optionalString(body.run_id), metadata: isRecord(body.metadata) ? body.metadata : undefined, apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "usage") {
          return { status_code: 200, body: this.service.usageSnapshot(tenantId, projectId, { authKeyId }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "quota") {
          return { status_code: 200, body: this.service.usageSnapshot(tenantId, projectId, { authKeyId }) };
        }
        if (parts.length >= 6 && parts[3] === "commercial-auth-payment") {
          if (upperMethod === "POST" && parts.length === 6 && parts[4] === "oauth-providers" && parts[5] === "configure") {
            return { status_code: 201, body: this.service.configureOauthProvider(tenantId, projectId, {
              provider: String(body.provider ?? ""),
              clientIdRef: String(body.client_id_ref ?? ""),
              clientSecretRef: String(body.client_secret_ref ?? ""),
              redirectUris: arrayOfStrings(body.redirect_uris),
              scopes: arrayOfStrings(body.scopes),
              configId: optionalString(body.config_id),
              authKeyId,
            }) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[4] === "oauth-authorizations" && parts[5] === "begin") {
            return { status_code: 201, body: this.service.beginOauthAuthorization(tenantId, projectId, {
              providerConfigId: String(body.provider_config_id ?? ""),
              redirectUri: String(body.redirect_uri ?? ""),
              codeVerifier: String(body.code_verifier ?? ""),
              state: optionalString(body.state),
              authKeyId,
            }) };
          }
          if (upperMethod === "POST" && parts.length === 7 && parts[4] === "oauth-authorizations" && parts[6] === "complete") {
            return { status_code: 200, body: this.service.completeOauthAuthorization(tenantId, projectId, {
              flowId: parts[5],
              state: String(body.state ?? ""),
              codeVerifier: String(body.code_verifier ?? ""),
              redirectUri: String(body.redirect_uri ?? ""),
              subjectRef: String(body.subject_ref ?? ""),
              providerCodeRef: optionalString(body.provider_code_ref),
              providerError: optionalString(body.provider_error),
              accessTokenRef: optionalString(body.access_token_ref),
              refreshTokenRef: optionalString(body.refresh_token_ref),
              sessionId: optionalString(body.session_id),
              authKeyId,
            }) };
          }
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "audit-log") {
          return { status_code: 200, body: this.service.auditSnapshot(tenantId, projectId, { authKeyId, runId: optionalString(body.run_id), actionPrefix: optionalString(body.action_prefix), limit: body.limit === undefined ? undefined : Number(body.limit) }) };
        }
        if (upperMethod === "POST" && parts.length === 5 && parts[3] === "worker-jobs" && parts[4] === "enqueue") {
          return { status_code: 202, body: this.service.enqueueWorkerJob(tenantId, projectId, { jobType: String(body.job_type ?? ""), targetId: optionalString(body.target_id), payload: isRecord(body.payload) ? body.payload : {}, jobId: optionalString(body.job_id), priority: body.priority === undefined ? undefined : Number(body.priority), maxAttempts: body.max_attempts === undefined ? undefined : Number(body.max_attempts), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
        }
        if (upperMethod === "POST" && parts.length === 5 && parts[3] === "worker-jobs" && parts[4] === "lease") {
          return { status_code: 200, body: this.service.leaseWorkerJob(tenantId, projectId, { leaseOwnerId: String(body.lease_owner_id ?? ""), leaseSeconds: body.lease_seconds === undefined ? undefined : Number(body.lease_seconds), jobType: optionalString(body.job_type), apiKeyId: authKeyId, requestId: optionalString(body.request_id) }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "worker-jobs") {
          return { status_code: 200, body: this.service.listWorkerJobs(tenantId, projectId, { status: optionalString(body.status), jobType: optionalString(body.job_type), limit: body.limit === undefined ? undefined : Number(body.limit), authKeyId }) };
        }
        if (parts.length === 6 && parts[3] === "worker-jobs") {
          const jobId = parts[4];
          if (upperMethod === "POST" && parts[5] === "heartbeat") {
            return { status_code: 200, body: this.service.heartbeatWorkerJob(tenantId, projectId, jobId, { leaseOwnerId: String(body.lease_owner_id ?? ""), leaseSeconds: body.lease_seconds === undefined ? undefined : Number(body.lease_seconds), apiKeyId: authKeyId, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts[5] === "complete") {
            return { status_code: 200, body: this.service.completeWorkerJob(tenantId, projectId, jobId, isRecord(body.result) ? body.result : {}, { leaseOwnerId: String(body.lease_owner_id ?? ""), apiKeyId: authKeyId, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts[5] === "fail") {
            return { status_code: 200, body: this.service.failWorkerJob(tenantId, projectId, jobId, isRecord(body.error) ? body.error : {}, { leaseOwnerId: String(body.lease_owner_id ?? ""), retryAfterSeconds: body.retry_after_seconds === undefined ? undefined : Number(body.retry_after_seconds), apiKeyId: authKeyId, requestId: optionalString(body.request_id) }) };
          }
        }
        if (upperMethod === "POST" && parts.length === 5 && parts[3] === "audit-chain" && parts[4] === "verify") {
          return { status_code: 200, body: this.service.verifyAuditChain(tenantId, projectId, { authKeyId, requestId: optionalString(body.request_id) }) };
        }
        if (parts.length >= 6 && parts[3] === "runs") {
          const runId = parts[4];
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "upload") {
            return { status_code: 202, body: this.service.uploadRunResult(tenantId, projectId, runId, isRecord(body.result) ? body.result : body, { uploadId: optionalString(body.upload_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "trace-events") {
            return { status_code: 202, body: this.service.ingestTrace(tenantId, projectId, runId, Array.isArray(body.observations) ? (body.observations.filter(isRecord) as JsonRecord[]) : [], { batchId: optionalString(body.batch_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "lifecycle") {
            return { status_code: 200, body: this.service.lifecycleSnapshot(tenantId, projectId, runId) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "release-gate") {
            return { status_code: 200, body: this.service.evaluateReleaseGate(tenantId, projectId, runId, { evaluator: optionalString(body.evaluator), minScore: body.min_score === undefined ? undefined : Number(body.min_score), requiredTraceCompleteness: body.required_trace_completeness === undefined ? undefined : Number(body.required_trace_completeness), authKeyId, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "release-evidence") {
            return { status_code: 200, body: this.service.buildReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId }) };
          }
          if (upperMethod === "POST" && parts.length === 7 && parts[5] === "release-evidence" && parts[6] === "verify") {
            return { status_code: 200, body: this.service.verifyReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId, packet: isRecord(body.packet) ? body.packet : undefined, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "artifact-manifests") {
            return { status_code: 202, body: this.service.createArtifactManifest(tenantId, projectId, runId, isRecord(body.manifest) ? body.manifest : body, { artifactId: optionalString(body.artifact_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "artifact-manifests") {
            return { status_code: 200, body: { artifact_manifests: this.service.listArtifactManifests(tenantId, projectId, runId, { authKeyId }) } };
          }
        }
      }
      throw new ValidationError(`unsupported route: ${upperMethod} ${path}`);
    } catch (error) {
      const code = error instanceof Error && "code" in error ? String((error as Error & { code?: string }).code) : "validation_error";
      return { status_code: code === "not_found" ? 404 : 400, body: { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, error: { code, message: error instanceof Error ? error.message : String(error) } } };
    }
  }
}


export class SaaSHttpJsonTransport implements SaaSClientTransport {
  readonly baseUrl: string;
  readonly headers: Record<string, string>;
  private readonly fetchImpl: SaaSFetchLike;

  constructor(options: SaaSHttpTransportOptions) {
    if (!options.baseUrl || !String(options.baseUrl).trim()) throw new ValidationError("baseUrl must be a non-empty string");
    const candidate = options.fetch ?? (globalThis.fetch as unknown as SaaSFetchLike | undefined);
    if (candidate === undefined) throw new ValidationError("fetch implementation is required for SaaS HTTP transport");
    this.baseUrl = String(options.baseUrl).replace(/\/+$/, "");
    this.headers = { ...(options.headers ?? {}) };
    const bearerApiKey = options.bearerApiKey ?? options.apiKeySecret;
    if (bearerApiKey !== undefined && bearerApiKey.trim() !== "") {
      this.headers.Authorization = bearerAuthorizationHeader(bearerApiKey);
    }
    this.fetchImpl = candidate;
  }

  async requestJson(method: string, path: string, body: JsonRecord = {}, options: { headers?: Record<string, string> } = {}): Promise<JsonRecord> {
    const upperMethod = method.toUpperCase();
    const url = new URL(path.startsWith("/") ? path : `/${path}`, `${this.baseUrl}/`);
    const init: { method: string; headers: Record<string, string>; body?: string } = {
      method: upperMethod,
      headers: { accept: "application/json", ...this.headers, ...(options.headers ?? {}) },
    };
    if (upperMethod === "GET") {
      for (const [key, value] of Object.entries(body)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
      }
    } else {
      init.headers["content-type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const response = await this.fetchImpl(url, init);
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = { error: { code: "invalid_json", message: await response.text() } };
    }
    if (!isRecord(payload)) {
      throw new ValidationError(`SaaS HTTP response must be a JSON object for ${upperMethod} ${url.pathname}`);
    }
    if (!response.ok) {
      const err = isRecord(payload.error) ? payload.error : {};
      throw new ValidationError(String(err.message ?? `SaaS HTTP request failed with status ${response.status}`));
    }
    return payload;
  }
}

export function saasHealthz(): JsonRecord {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    status: "ok",
    local_only: true,
    ashr_api_used: false,
    service: "ashr-saas-control-plane",
    client_version: SAAS_CLIENT_VERSION,
    openapi_path: "/openapi.json",
    legacy_openapi_path: "/healthz/openapi",
  };
}

export function exportSaaSOpenApiSpec(options: { title?: string; version?: string; serverUrl?: string } = {}): JsonRecord {
  const title = options.title ?? "Ashr SaaS Control Plane Runtime";
  const version = options.version ?? CONTROL_PLANE_SCHEMA_VERSION;
  const serverUrl = options.serverUrl ?? "http://localhost";
  const json = { "application/json": { schema: { type: "object", additionalProperties: true } } };
  const response = (description: string): JsonRecord => ({ description, content: json });
  return {
    openapi: CONTROL_PLANE_OPENAPI_VERSION,
    info: { title, version, description: "Local hosted/self-host control-plane HTTP adapter for SaaSControlPlaneRouter.", "x-schema-version": SAAS_OPENAPI_SCHEMA_VERSION, "x-client-version": SAAS_CLIENT_VERSION },
    servers: [{ url: serverUrl }],
    paths: {
      "/healthz": { get: { operationId: "healthz", responses: { "200": response("Health check") } } },
      "/openapi.json": { get: { operationId: "exportOpenApi", responses: { "200": response("OpenAPI document") } } },
      "/v1/openapi.json": { get: { operationId: "exportOpenApiV1", responses: { "200": response("OpenAPI document") } } },
      "/healthz/openapi": { get: { operationId: "exportOpenApiLegacy", responses: { "200": response("OpenAPI document") } } },
      "/v1/bootstrap": { post: { operationId: "bootstrapProject", requestBody: { content: json }, responses: { "201": response("Bootstrap result") } } },
      "/v1/projects/{project_id}/api-keys": {
        get: { operationId: "listApiKeys", parameters: pathTenantParameters(), responses: { "200": response("API keys") } },
        post: { operationId: "createApiKey", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "201": response("API key") } },
      },
      "/v1/projects/{project_id}/api-keys/{key_id}/authenticate": { post: { operationId: "authenticateApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Authentication result") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/verify": { post: { operationId: "verifyApiKeySecret", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Secret verification result") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/rate-limit": {
        post: { operationId: "configureApiKeyRateLimit", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("API key rate limit") } },
      },
      "/v1/projects/{project_id}/api-keys/rate-limits": { get: { operationId: "apiKeyRateLimitSnapshot", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], responses: { "200": response("API key rate limit snapshot") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/revoke": { post: { operationId: "revokeApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Revocation result") } } },
      "/v1/projects/{project_id}/sdk-submit": { post: { operationId: "sdkSubmit", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "202": response("Submitted run") } } },
      "/v1/projects/{project_id}/runs/{run_id}/upload": { post: { operationId: "uploadRun", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Uploaded run result") } } },
      "/v1/projects/{project_id}/runs/{run_id}/trace-events": { post: { operationId: "ingestTrace", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Trace batch") } } },
      "/v1/projects/{project_id}/runs/{run_id}/lifecycle": { get: { operationId: "lifecycle", parameters: pathTenantParameters("run_id"), responses: { "200": response("Run lifecycle") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-gate": { post: { operationId: "evaluateReleaseGate", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "200": response("Release gate decision") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-evidence": { get: { operationId: "buildReleaseEvidencePacket", parameters: pathTenantParameters("run_id"), responses: { "200": response("Release evidence packet") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": { post: { operationId: "verifyReleaseEvidencePacket", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "200": response("Release evidence packet verification") } } },
      "/v1/projects/{project_id}/quota": { get: { operationId: "quotaSnapshot", parameters: pathTenantParameters(), responses: { "200": response("Quota snapshot") } } },
      "/v1/projects/{project_id}/usage": { get: { operationId: "usageSnapshot", parameters: pathTenantParameters(), responses: { "200": response("Usage ledger snapshot") } } },
      "/v1/projects/{project_id}/commercial-auth-payment/oauth-providers/configure": { post: { operationId: "configureOauthProvider", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "201": response("OAuth provider configuration") } } },
      "/v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/begin": { post: { operationId: "beginOauthAuthorization", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "201": response("OAuth authorization flow") } } },
      "/v1/projects/{project_id}/commercial-auth-payment/oauth-authorizations/{flow_id}/complete": { post: { operationId: "completeOauthAuthorization", parameters: pathTenantParameters("flow_id"), requestBody: { content: json }, responses: { "200": response("OAuth authorization completion") } } },
      "/v1/projects/{project_id}/billing/checkout-plan": { post: { operationId: "billingCheckoutPlan", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Billing checkout plan") } } },
      "/v1/projects/{project_id}/billing/portal-plan": { post: { operationId: "billingPortalPlan", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Billing portal plan") } } },
      "/v1/projects/{project_id}/billing/webhooks/ingest": { post: { operationId: "billingWebhookIngest", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Billing webhook ingest") } } },
      "/v1/projects/{project_id}/billing/ledger": { get: { operationId: "billingLedger", parameters: pathTenantParameters(), responses: { "200": response("Billing ledger") } } },
      "/v1/projects/{project_id}/audit-log": { get: { operationId: "auditSnapshot", parameters: pathTenantParameters(), responses: { "200": response("Audit log snapshot") } } },
      "/v1/projects/{project_id}/worker-jobs": { get: { operationId: "listWorkerJobs", parameters: pathTenantParameters(), responses: { "200": response("Worker jobs") } } },
      "/v1/projects/{project_id}/worker-jobs/enqueue": { post: { operationId: "enqueueWorkerJob", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "202": response("Enqueued worker job") } } },
      "/v1/projects/{project_id}/worker-jobs/lease": { post: { operationId: "leaseWorkerJob", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Leased worker job") } } },
      "/v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat": { post: { operationId: "heartbeatWorkerJob", parameters: pathTenantParameters("job_id"), requestBody: { content: json }, responses: { "200": response("Worker job heartbeat") } } },
      "/v1/projects/{project_id}/worker-jobs/{job_id}/complete": { post: { operationId: "completeWorkerJob", parameters: pathTenantParameters("job_id"), requestBody: { content: json }, responses: { "200": response("Completed worker job") } } },
      "/v1/projects/{project_id}/worker-jobs/{job_id}/fail": { post: { operationId: "failWorkerJob", parameters: pathTenantParameters("job_id"), requestBody: { content: json }, responses: { "200": response("Failed worker job") } } },
      "/v1/projects/{project_id}/audit-chain/verify": { post: { operationId: "verifyAuditChain", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Audit chain verification") } } },
      "/v1/projects/{project_id}/runs/{run_id}/artifact-manifests": {
        get: { operationId: "listArtifactManifests", parameters: pathTenantParameters("run_id"), responses: { "200": response("Artifact manifests") } },
        post: { operationId: "createArtifactManifest", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Artifact manifest receipt") } },
      },
    },
    components: { schemas: { JsonRecord: { type: "object", additionalProperties: true } } },
    "x-local-only": true,
    "x-ashr-api-used": false,
  };
}

export function hostedRouteScopeManifest(): JsonRecord {
  return {
    schema_version: "ashr.clone.hosted_route_scope_manifest.v1",
    client: "typescript",
    public_safe: true,
    source_policy: { private_evidence_read: false, raw_payloads_included: false, tokens_included: false },
    routes: Object.keys(HOSTED_ROUTE_SCOPE_REQUIREMENTS).sort().map((route) => ({
      route,
      required_scopes: [...HOSTED_ROUTE_SCOPE_REQUIREMENTS[route]],
    })),
  };
}

export function consumeGoRouteScopeManifest(manifest: JsonRecord | string): JsonRecord {
  const snapshot = typeof manifest === "string" ? JSON.parse(readFileSync(assertPublicManifestPath(manifest), "utf8")) as JsonRecord : manifest;
  if (snapshot.public_safe !== true) throw new ValidationError("route/scope manifest must be public_safe");
  const safeSourcePolicy = { private_evidence_read: false, raw_payloads_included: false, tokens_included: false };
  const sourcePolicy = isRecord(snapshot.source_policy)
    ? snapshot.source_policy
    : snapshot.raw_payloads_included === false
      ? safeSourcePolicy
      : {};
  if (sourcePolicy.private_evidence_read !== false || sourcePolicy.raw_payloads_included !== false || sourcePolicy.tokens_included !== false) {
    throw new ValidationError("route/scope manifest has unsafe source policy");
  }
  const goRoutes = new Set((Array.isArray(snapshot.go_manifest_routes) ? snapshot.go_manifest_routes : []).map((route) => String(route)));
  if (goRoutes.size === 0) {
    for (const route of goRoutesFromOpenApi(snapshot)) goRoutes.add(route);
  }
  const hostedRoutes = new Set(Object.keys(HOSTED_ROUTE_SCOPE_REQUIREMENTS));
  const consumableGoRoutes = [...goRoutes].filter((route) => hostedRoutes.has(route)).sort();
  const unsupportedGoRoutes = [...goRoutes].filter((route) => !hostedRoutes.has(route)).sort();
  const unsupportedGoRouteGaps = validateUnsupportedGoRouteGaps(goRoutes, hostedRoutes);
  const routeScopeDocs = extractGoRouteScopeDocs(snapshot);
  return {
    schema_version: "ashr.clone.go_route_scope_consumption.v1",
    client: "typescript",
    public_safe: true,
    source_policy: safeSourcePolicy,
    consumable_go_routes: consumableGoRoutes,
    unsupported_go_routes: unsupportedGoRoutes,
    unsupported_go_route_gaps: unsupportedGoRouteGaps,
    client_only_routes: [...hostedRoutes].filter((route) => !goRoutes.has(route)).sort(),
    route_scopes: consumableGoRoutes.map((route) => ({ route, required_scopes: [...HOSTED_ROUTE_SCOPE_REQUIREMENTS[route]] })),
    route_scope_docs: routeScopeDocs === undefined ? null : consumeGoRouteScopeDocs(routeScopeDocs),
  };
}

export function consumeOfficialApiMutatingCalibrationIndex(index: JsonRecord | string): JsonRecord {
  const snapshot = typeof index === "string" ? JSON.parse(readFileSync(assertPublicManifestPath(index), "utf8")) as JsonRecord : { ...index };
  if (snapshot.schema_version !== MUTATING_CALIBRATION_INDEX_SCHEMA_VERSION) throw new ValidationError("official API mutating calibration index schema_version drift");
  if (snapshot.public_safe !== true || snapshot.raw_payloads_included !== false || snapshot.secret_values_included !== false) {
    throw new ValidationError("official API mutating calibration index must be public-safe");
  }
  if (!Array.isArray(snapshot.records)) throw new ValidationError("official API mutating calibration index records must be an array");

  const byModality = new Map<string, JsonRecord>();
  for (const rawRecord of snapshot.records) {
    if (!isRecord(rawRecord)) throw new ValidationError("official API mutating calibration index record must be an object");
    const modalities = Array.isArray(rawRecord.summary_modalities) ? rawRecord.summary_modalities.map((item) => String(item)) : [];
    if (modalities.length !== 1) throw new ValidationError("official API mutating calibration index record must bind one modality");
    const modality = modalities[0];
    if (!(MUTATING_CALIBRATION_MODALITIES as readonly string[]).includes(modality)) throw new ValidationError(`official API mutating calibration index has unsupported modality: ${modality}`);
    const stepIds = Array.isArray(rawRecord.mutating_step_ids) ? rawRecord.mutating_step_ids.map((item) => String(item)) : [];
    const expectedStep = `create-request-${modality}`;
    if (!stepIds.includes(expectedStep)) throw new ValidationError(`official API mutating calibration index missing ${expectedStep}`);
    const privateManifest = typeof rawRecord.private_manifest === "string" ? rawRecord.private_manifest : "";
    if (!privateManifest.startsWith("docs/evidence/private_refs/")) throw new ValidationError("official API mutating calibration index record must point to ignored private evidence");
    if (rawRecord.raw_payloads_included !== false) throw new ValidationError("official API mutating calibration index record must exclude raw payloads");
    byModality.set(modality, {
      modality,
      status: rawRecord.status,
      quota_block_count: numberOrZero(rawRecord.quota_block_count),
      observed_error_kinds: Array.isArray(rawRecord.observed_error_kinds) ? rawRecord.observed_error_kinds.map((item) => String(item)).sort() : [],
      mutating_step_ids: stepIds,
      private_manifest: privateManifest,
      read_steps: numberOrZero(rawRecord.read_steps),
      total_steps: numberOrZero(rawRecord.total_steps),
    });
  }

  const missing = MUTATING_CALIBRATION_MODALITIES.filter((modality) => !byModality.has(modality));
  if (missing.length > 0) throw new ValidationError(`official API mutating calibration index missing modalities: ${missing.join(",")}`);

  const records = MUTATING_CALIBRATION_MODALITIES.map((modality) => byModality.get(modality) as JsonRecord);
  return {
    schema_version: "ashr.clone.official_api_mutating_calibration_consumption.v1",
    client: "typescript",
    public_safe: true,
    modalities: [...MUTATING_CALIBRATION_MODALITIES],
    quota_blocked_modalities: records.filter((record) => numberOrZero(record.quota_block_count) > 0).map((record) => String(record.modality)),
    records,
  };
}

function numberOrZero(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function goRoutesFromOpenApi(snapshot: JsonRecord): Set<string> {
  const routes = new Set<string>();
  if (isRecord(snapshot.paths)) {
    for (const [path, pathItem] of Object.entries(snapshot.paths)) {
      if (!isRecord(pathItem)) continue;
      for (const method of ["get", "post", "put", "patch", "delete"]) {
        if (Object.prototype.hasOwnProperty.call(pathItem, method)) routes.add(`${method.toUpperCase()} ${path}`);
      }
    }
  }
  if (Array.isArray(snapshot.routes)) {
    for (const route of snapshot.routes) {
      if (typeof route === "string" && route.includes(" ")) routes.add(route);
    }
  }
  return routes;
}

function extractGoRouteScopeDocs(snapshot: JsonRecord): JsonRecord | undefined {
  for (const key of ["route_scope_docs", "go_route_scope_docs"]) {
    if (isRecord(snapshot[key])) return snapshot[key] as JsonRecord;
  }
  if (isRecord(snapshot.artifact)) return extractGoRouteScopeDocs(snapshot.artifact as JsonRecord);
  if (isRecord(snapshot.payload)) return extractGoRouteScopeDocs(snapshot.payload as JsonRecord);
  return undefined;
}

function consumeGoRouteScopeDocs(docs: JsonRecord): JsonRecord {
  if (docs.schema_version !== "ashr.clone.go_route_scope_docs.v1") throw new ValidationError("route_scope_docs schema_version drift");
  if (docs.public_safe !== true || docs.raw_payloads_included !== false) {
    throw new ValidationError("route_scope_docs must be public-safe and exclude raw payloads");
  }
  if (docs.source !== "generated_from_go_route_manifest") throw new ValidationError("route_scope_docs source drift");

  const groups = new Map<string, JsonRecord>();
  for (const group of Array.isArray(docs.route_groups) ? docs.route_groups : []) {
    if (isRecord(group)) groups.set(String(group.name), group);
  }
  const requiredGroups = new Set(["usage_quota", "run_lifecycle", "audit"]);
  const missingGroups = [...requiredGroups].filter((name) => !groups.has(name)).sort();
  if (missingGroups.length > 0) throw new ValidationError(`route_scope_docs missing route families: ${missingGroups.join(",")}`);

  assertRouteScopeGroup(groups.get("usage_quota")!, "usage_quota", new Set(["GET /v1/projects/{project_id}/usage", "GET /v1/projects/{project_id}/quota", "POST /v1/projects/{project_id}/usage/quotas", "POST /v1/projects/{project_id}/quota/limits"]), new Set(["usage:read"]));
  assertRouteScopeGroup(groups.get("run_lifecycle")!, "run_lifecycle", new Set(["GET /v1/projects/{project_id}/runs/{run_id}/lifecycle"]), new Set(["run:lifecycle:read"]));
  assertRouteScopeGroup(groups.get("audit")!, "audit", new Set(["GET /v1/projects/{project_id}/audit-log", "POST /v1/projects/{project_id}/audit-chain/verify"]), new Set(["audit:read"]));

  const planMetrics = new Map<string, JsonRecord>();
  for (const metric of Array.isArray(docs.plan_metrics) ? docs.plan_metrics : []) {
    if (isRecord(metric)) planMetrics.set(String(metric.metric), metric);
  }
  const requiredMetrics = new Set(["graded_scenarios", "observations", "voice_minutes", "projects"]);
  const missingMetrics = [...requiredMetrics].filter((metric) => !planMetrics.has(metric)).sort();
  if (missingMetrics.length > 0) throw new ValidationError(`route_scope_docs missing plan metrics: ${missingMetrics.join(",")}`);

  const planLimits = new Map<string, JsonRecord>();
  for (const plan of Array.isArray(docs.plan_limits) ? docs.plan_limits : []) {
    if (isRecord(plan)) planLimits.set(String(plan.plan), plan);
  }
  for (const planName of ["Developer", "Startup"]) {
    const plan = planLimits.get(planName);
    if (plan === undefined) throw new ValidationError(`route_scope_docs missing plan limit docs: ${planName}`);
    const limits = new Set((Array.isArray(plan.limits) ? plan.limits : []).filter(isRecord).map((limit) => String(limit.metric)));
    const missingLimits = [...requiredMetrics].filter((metric) => !limits.has(metric)).sort();
    if (missingLimits.length > 0) throw new ValidationError(`route_scope_docs missing ${planName} limits: ${missingLimits.join(",")}`);
  }

  return {
    schema_version: docs.schema_version,
    source: docs.source,
    public_safe: true,
    route_families: [...requiredGroups].sort(),
    plan_metrics: [...planMetrics.keys()].sort(),
    plan_limits: [...planLimits.keys()].sort(),
  };
}

function assertRouteScopeGroup(group: JsonRecord, name: string, routes: Set<string>, scopes: Set<string>): void {
  const groupRoutes = new Set((Array.isArray(group.routes) ? group.routes : []).map((route) => String(route)));
  const groupScopes = new Set((Array.isArray(group.scopes) ? group.scopes : []).map((scope) => String(scope)));
  const missingRoutes = [...routes].filter((route) => !groupRoutes.has(route)).sort();
  if (missingRoutes.length > 0) throw new ValidationError(`route_scope_docs ${name} missing routes: ${missingRoutes.join(",")}`);
  const missingScopes = [...scopes].filter((scope) => !groupScopes.has(scope)).sort();
  if (missingScopes.length > 0) throw new ValidationError(`route_scope_docs ${name} missing scopes: ${missingScopes.join(",")}`);
}

function validateUnsupportedGoRouteGaps(goRoutes: Set<string>, hostedRoutes: Set<string>): JsonRecord[] {
  const unsupportedRoutes = [...goRoutes].filter((route) => !hostedRoutes.has(route)).sort();
  const declaredRoutes = Object.keys(UNSUPPORTED_GO_ROUTE_GAPS).sort();
  const missingRoutes = unsupportedRoutes.filter((route) => !Object.prototype.hasOwnProperty.call(UNSUPPORTED_GO_ROUTE_GAPS, route));
  const staleRoutes = declaredRoutes.filter((route) => !goRoutes.has(route) || hostedRoutes.has(route));
  if (missingRoutes.length > 0 || staleRoutes.length > 0) {
    throw new ValidationError(`Go route/scope gap registry drift: missing=${missingRoutes.join(",") || "none"}; stale=${staleRoutes.join(",") || "none"}`);
  }
  return unsupportedRoutes.map((route) => ({ route, ...UNSUPPORTED_GO_ROUTE_GAPS[route] }));
}

function assertPublicManifestPath(inputPath: string): string {
  const lowerParts = resolve(inputPath).toLowerCase().split(/[\\/]+/u);
  if (lowerParts.includes("private_refs") || lowerParts.includes(".secrets")) {
    throw new SecretInputError("refusing to read private_refs or .secrets input paths");
  }
  return inputPath;
}



export class SecretInputError extends Error {
  code = "secret_input_error";
}

export class SaaSIngestionClient {
  readonly service: SaaSControlPlaneService;
  readonly transport?: SaaSClientTransport;

  constructor(options: { service?: SaaSControlPlaneService; transport?: SaaSClientTransport; baseUrl?: string; fetch?: SaaSFetchLike; headers?: Record<string, string>; bearerApiKey?: string; apiKeySecret?: string } = {}) {
    this.service = options.service ?? new SaaSControlPlaneService();
    this.transport = options.transport ?? (options.baseUrl !== undefined ? new SaaSHttpJsonTransport({ baseUrl: options.baseUrl, fetch: options.fetch, headers: options.headers, bearerApiKey: options.bearerApiKey, apiKeySecret: options.apiKeySecret }) : undefined);
  }

  static forBaseUrl(baseUrl: string, options: { fetch?: SaaSFetchLike; headers?: Record<string, string>; bearerApiKey?: string; apiKeySecret?: string } = {}): SaaSIngestionClient {
    return new SaaSIngestionClient({ baseUrl, fetch: options.fetch, headers: options.headers, bearerApiKey: options.bearerApiKey, apiKeySecret: options.apiKeySecret });
  }

  async requestJson(method: string, path: string, body: JsonRecord = {}, options: { headers?: Record<string, string> } = {}): Promise<JsonRecord> {
    if (this.transport !== undefined) return this.transport.requestJson(method, path, body, options);
    return new SaaSControlPlaneRouter(this.service).handle(method, path, body, options).body;
  }

  async healthz(): Promise<JsonRecord> {
    return this.requestJson("GET", "/healthz");
  }

  async openApi(options: { serverUrl?: string } = {}): Promise<JsonRecord> {
    if (this.transport !== undefined) return this.requestJson("GET", "/openapi.json");
    return exportSaaSOpenApiSpec({ serverUrl: options.serverUrl });
  }

  static async fromStateFile(inputPath: string): Promise<SaaSIngestionClient> {
    return new SaaSIngestionClient({ service: await SaaSControlPlaneService.fromStateFile(inputPath) });
  }

  async writeState(outputPath: string): Promise<string> {
    return this.service.writeState(outputPath);
  }

  snapshotState(): SaaSControlPlaneState {
    return this.service.snapshotState();
  }

  bootstrapProject(options: { tenantName: string; projectName: string; tenantId?: string; projectId?: string; datasetId?: string; datasetName?: string; cases?: JsonRecord[] }): JsonRecord {
    const result = this.service.bootstrapProject(options);
    if (options.datasetId !== undefined) {
      const tenant = result.tenant as JsonRecord;
      const project = result.project as JsonRecord;
      result.dataset = this.service.cloud.createDataset(String(tenant.tenant_id), String(project.project_id), {
        datasetId: options.datasetId,
        name: options.datasetName ?? "SDK Bootstrap Dataset",
        cases: options.cases ?? [{ id: "sdk-bootstrap-case", prompt: "local bootstrap", expected: { text: "local bootstrap" } }],
        metadata: { created_by: "ashr_clone.ts_saas_client", local_only: true },
      });
    }
    return envelope("bootstrap_project", result);
  }

  async bootstrapProjectHttp(options: { tenantName?: string; tenant_name?: string; projectName?: string; project_name?: string; tenantId?: string; tenant_id?: string; projectId?: string; project_id?: string; datasetId?: string; dataset_id?: string; datasetName?: string; dataset_name?: string; cases?: JsonRecord[] }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", "/v1/bootstrap", {
      tenant_name: clientRequiredString(options, "tenantName", "tenant_name"),
      project_name: clientRequiredString(options, "projectName", "project_name"),
      tenant_id: clientString(options, "tenantId", "tenant_id"),
      project_id: clientString(options, "projectId", "project_id"),
      dataset_id: clientString(options, "datasetId", "dataset_id"),
      dataset_name: clientString(options, "datasetName", "dataset_name"),
      cases: options.cases,
    });
    return envelope("bootstrap_project", body);
  }
  createApiKey(tenantId: string, projectId: string, options: SaaSClientOptions & { name: string; scopes: string[] } & { keyId?: string; authKeyId?: string; revealSecret?: boolean; apiKey?: string } ): SaaSClientEnvelope<SaaSApiKeyCreateResult, "create_api_key"> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("create_api_key", this.service.createApiKey(tenantId, projectId, {
      name: String(options.name),
      scopes: arrayOfStrings(options.scopes),
      keyId: clientString(options, "keyId", "key_id"),
      authKeyId: clientString(options, "authKeyId", "auth_key_id"),
      revealSecret: clientBool(options, "revealSecret", "reveal_secret"),
    }) as SaaSApiKeyCreateResult);
  }

  verifyApiKeySecret(tenantId: string, projectId: string, options: SaaSClientOptions & { keyId?: string; key_id?: string; secret: string; scope?: string }): SaaSClientEnvelope<SaaSApiKeyVerificationResult, "verify_api_key_secret"> {
    return envelope("verify_api_key_secret", this.service.verifyApiKeySecret(tenantId, projectId, {
      keyId: clientRequiredString(options, "keyId", "key_id"),
      secret: String(options.secret),
      scope: clientString(options, "scope"),
    }) as SaaSApiKeyVerificationResult);
  }

  configureApiKeyRateLimit(tenantId: string, projectId: string, options: SaaSClientOptions & { keyId?: string; key_id?: string; operation: string; limit: number; period?: string; authKeyId?: string; auth_key_id?: string }): SaaSClientEnvelope<SaaSApiKeyRateLimit, "configure_api_key_rate_limit"> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("configure_api_key_rate_limit", this.service.configureApiKeyRateLimit(tenantId, projectId, {
      keyId: clientRequiredString(options, "keyId", "key_id"),
      operation: String(options.operation),
      limit: Number(options.limit),
      period: clientString(options, "period"),
      authKeyId: clientString(options, "authKeyId", "auth_key_id"),
    }) as SaaSApiKeyRateLimit);
  }

  apiKeyRateLimitSnapshot(tenantId: string, projectId: string, options: SaaSClientOptions & { keyId?: string; key_id?: string } = {}): SaaSClientEnvelope<SaaSApiKeyRateLimitSnapshot, "api_key_rate_limit_snapshot"> {
    return envelope("api_key_rate_limit_snapshot", this.service.apiKeyRateLimitSnapshot(tenantId, projectId, { keyId: clientString(options, "keyId", "key_id") }) as SaaSApiKeyRateLimitSnapshot);
  }

  listApiKeys(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; apiKey?: string } = {}): SaaSClientEnvelope<SaaSApiKeyListResult, "list_api_keys"> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("list_api_keys", { api_keys: this.service.listApiKeys(tenantId, projectId, { authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSApiKeyRecord[] });
  }

  revokeApiKey(tenantId: string, projectId: string, keyId: string, options: SaaSClientOptions & { authKeyId?: string; apiKey?: string } = {}): SaaSClientEnvelope<SaaSApiKeyRecord, "revoke_api_key"> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("revoke_api_key", this.service.revokeApiKey(tenantId, projectId, keyId, { authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSApiKeyRecord);
  }

  sdkSubmit(tenantId: string, projectId: string, options: SaaSClientOptions & { datasetId?: string; dataset_id?: string; agentRef?: string; agent_ref?: string; metadata?: JsonRecord; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string }): JsonRecord {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("sdk_submit", this.service.sdkSubmitRun(tenantId, projectId, {
      datasetId: clientRequiredString(options, "datasetId", "dataset_id"),
      agentRef: clientRequiredString(options, "agentRef", "agent_ref"),
      runId: clientString(options, "runId", "run_id"),
      metadata: { client: SAAS_CLIENT_VERSION, ...(options.metadata ?? {}) },
      apiKeyId: clientString(options, "apiKeyId", "api_key_id"),
      idempotencyKey: clientString(options, "idempotencyKey", "idempotency_key"),
      requestId: clientString(options, "requestId", "request_id"),
    }));
  }

  uploadRun(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: SaaSClientOptions & { uploadId?: string; upload_id?: string; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string } = {}): JsonRecord {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("upload_run", this.service.uploadRunResult(tenantId, projectId, runId, result, clientUploadOptions(options)));
  }

  ingestTrace(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: SaaSClientOptions & { batchId?: string; batch_id?: string; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string } = {}): SaaSClientEnvelope<SaaSTraceIngestResult, "ingest_trace"> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("ingest_trace", this.service.ingestTrace(tenantId, projectId, runId, observations, clientTraceOptions(options)) as SaaSTraceIngestResult);
  }

  lifecycle(tenantId: string, projectId: string, runId: string): JsonRecord {
    return envelope("lifecycle", this.service.lifecycleSnapshot(tenantId, projectId, runId));
  }

  usage(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord {
    return envelope("usage", this.service.usageSnapshot(tenantId, projectId, options));
  }

  quotaSnapshot(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): SaaSClientEnvelope<SaaSQuotaSnapshotResult, "quota_snapshot"> {
    return envelope("quota_snapshot", this.service.usageSnapshot(tenantId, projectId, { authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSQuotaSnapshotResult);
  }

  configureOauthProvider(tenantId: string, projectId: string, options: SaaSOAuthProviderConfigureOptions): SaaSClientEnvelope<SaaSOAuthProviderConfig, "configure_oauth_provider"> {
    return envelope("configure_oauth_provider", this.service.configureOauthProvider(tenantId, projectId, options));
  }

  beginOauthAuthorization(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationBeginOptions): SaaSClientEnvelope<SaaSOAuthAuthorizationBeginResult, "oauth_authorization_begin"> {
    return envelope("oauth_authorization_begin", this.service.beginOauthAuthorization(tenantId, projectId, options));
  }

  completeOauthAuthorization(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationCompleteOptions): SaaSClientEnvelope<SaaSOAuthAuthorizationCompleteResult, "oauth_authorization_complete"> {
    return envelope("oauth_authorization_complete", this.service.completeOauthAuthorization(tenantId, projectId, options));
  }

  billingCheckoutPlan(tenantId: string, projectId: string, options: SaaSBillingCheckoutOptions): SaaSClientEnvelope<SaaSBillingCheckoutPlan, "billing_checkout_plan"> {
    return envelope("billing_checkout_plan", this.service.billingCheckoutPlan(tenantId, projectId, { ...options, authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSBillingCheckoutPlan);
  }

  billingPortalPlan(tenantId: string, projectId: string, options: SaaSBillingPortalOptions): SaaSClientEnvelope<SaaSBillingPortalPlan, "billing_portal_plan"> {
    return envelope("billing_portal_plan", this.service.billingPortalPlan(tenantId, projectId, { ...options, authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSBillingPortalPlan);
  }

  billingWebhookIngest(tenantId: string, projectId: string, options: SaaSBillingWebhookOptions): SaaSClientEnvelope<SaaSBillingWebhookIngestResult, "billing_webhook_ingest"> {
    return envelope("billing_webhook_ingest", this.service.billingWebhookIngest(tenantId, projectId, { ...options, authKeyId: clientString(options, "authKeyId", "auth_key_id") }) as SaaSBillingWebhookIngestResult);
  }

  billingLedger(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): JsonRecord {
    return envelope("billing_ledger", this.service.billingLedgerSnapshot(tenantId, projectId, { authKeyId: clientString(options, "authKeyId", "auth_key_id") }));
  }

  auditLog(tenantId: string, projectId: string, options: SaaSClientOptions & { runId?: string; run_id?: string; actionPrefix?: string; action_prefix?: string; authKeyId?: string; auth_key_id?: string; limit?: number } = {}): JsonRecord {
    return envelope("audit_log", this.service.auditSnapshot(tenantId, projectId, {
      runId: clientString(options, "runId", "run_id"),
      actionPrefix: clientString(options, "actionPrefix", "action_prefix"),
      authKeyId: clientString(options, "authKeyId", "auth_key_id"),
      limit: options.limit === undefined ? undefined : Number(options.limit),
    }));
  }

  verifyAuditChain(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): JsonRecord {
    return envelope("audit_chain_verify", this.service.verifyAuditChain(tenantId, projectId, options));
  }

  evaluateReleaseGate(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): JsonRecord {
    return envelope("release_gate", this.service.evaluateReleaseGate(tenantId, projectId, runId, options));
  }

  buildReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string } = {}): JsonRecord {
    return envelope("release_evidence", this.service.buildReleaseEvidencePacket(tenantId, projectId, runId, options));
  }

  verifyReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): JsonRecord {
    return envelope("release_evidence_verify", this.service.verifyReleaseEvidencePacket(tenantId, projectId, runId, options));
  }

  createArtifactManifest(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): SaaSClientEnvelope<SaaSArtifactManifestResult, "artifact_manifest"> {
    return envelope("artifact_manifest", this.service.createArtifactManifest(tenantId, projectId, runId, manifest, options) as SaaSArtifactManifestResult);
  }

  listArtifactManifests(tenantId: string, projectId: string, runId?: string, options: { authKeyId?: string } = {}): SaaSClientEnvelope<SaaSArtifactManifestListResult, "artifact_manifests"> {
    return envelope("artifact_manifests", { artifact_manifests: this.service.listArtifactManifests(tenantId, projectId, runId, options) as SaaSArtifactManifestResult[] });
  }

  enqueueWorkerJob(tenantId: string, projectId: string, options: SaaSClientOptions & { jobType?: string; job_type?: string; targetId?: string; target_id?: string; payload?: JsonRecord; jobId?: string; job_id?: string; priority?: number; maxAttempts?: number; max_attempts?: number; apiKeyId?: string; api_key_id?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string }): JsonRecord {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    return envelope("worker_job_enqueue", this.service.enqueueWorkerJob(tenantId, projectId, {
      jobType: clientRequiredString(options, "jobType", "job_type"),
      targetId: clientString(options, "targetId", "target_id"),
      payload: options.payload,
      jobId: clientString(options, "jobId", "job_id"),
      priority: options.priority === undefined ? undefined : Number(options.priority),
      maxAttempts: options.maxAttempts === undefined && options.max_attempts === undefined ? undefined : Number(options.maxAttempts ?? options.max_attempts),
      apiKeyId: clientString(options, "apiKeyId", "api_key_id"),
      idempotencyKey: clientString(options, "idempotencyKey", "idempotency_key"),
      requestId: clientString(options, "requestId", "request_id"),
    }));
  }

  leaseWorkerJob(tenantId: string, projectId: string, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; leaseSeconds?: number; lease_seconds?: number; jobType?: string; job_type?: string; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): JsonRecord {
    return envelope("worker_job_lease", this.service.leaseWorkerJob(tenantId, projectId, { leaseOwnerId: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), leaseSeconds: Number(options.leaseSeconds ?? options.lease_seconds ?? 300), jobType: clientString(options, "jobType", "job_type"), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), requestId: clientString(options, "requestId", "request_id") }));
  }

  heartbeatWorkerJob(tenantId: string, projectId: string, jobId: string, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; leaseSeconds?: number; lease_seconds?: number; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): JsonRecord {
    return envelope("worker_job_heartbeat", this.service.heartbeatWorkerJob(tenantId, projectId, jobId, { leaseOwnerId: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), leaseSeconds: Number(options.leaseSeconds ?? options.lease_seconds ?? 300), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), requestId: clientString(options, "requestId", "request_id") }));
  }

  completeWorkerJob(tenantId: string, projectId: string, jobId: string, result: JsonRecord = {}, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): JsonRecord {
    return envelope("worker_job_complete", this.service.completeWorkerJob(tenantId, projectId, jobId, result, { leaseOwnerId: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), requestId: clientString(options, "requestId", "request_id") }));
  }

  failWorkerJob(tenantId: string, projectId: string, jobId: string, error: JsonRecord = {}, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; retryAfterSeconds?: number; retry_after_seconds?: number; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): JsonRecord {
    return envelope("worker_job_fail", this.service.failWorkerJob(tenantId, projectId, jobId, error, { leaseOwnerId: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), retryAfterSeconds: options.retryAfterSeconds === undefined && options.retry_after_seconds === undefined ? undefined : Number(options.retryAfterSeconds ?? options.retry_after_seconds), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), requestId: clientString(options, "requestId", "request_id") }));
  }

  listWorkerJobs(tenantId: string, projectId: string, options: SaaSClientOptions & { status?: string; jobType?: string; job_type?: string; limit?: number; authKeyId?: string; auth_key_id?: string } = {}): JsonRecord {
    return envelope("worker_jobs", this.service.listWorkerJobs(tenantId, projectId, { status: clientString(options, "status"), jobType: clientString(options, "jobType", "job_type"), limit: options.limit === undefined ? undefined : Number(options.limit), authKeyId: clientString(options, "authKeyId", "auth_key_id") }));
  }

  async enqueueWorkerJobHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { jobType?: string; job_type?: string; targetId?: string; target_id?: string; payload?: JsonRecord; jobId?: string; job_id?: string; priority?: number; maxAttempts?: number; max_attempts?: number; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs/enqueue`, { tenant_id: tenantId, job_type: clientRequiredString(options, "jobType", "job_type"), target_id: clientString(options, "targetId", "target_id"), payload: options.payload ?? {}, job_id: clientString(options, "jobId", "job_id"), priority: options.priority, max_attempts: options.maxAttempts ?? options.max_attempts, api_key_id: clientString(options, "apiKeyId", "api_key_id"), idempotency_key: clientString(options, "idempotencyKey", "idempotency_key"), request_id: clientString(options, "requestId", "request_id") });
    return envelope("worker_job_enqueue", body);
  }

  async leaseWorkerJobHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; leaseSeconds?: number; lease_seconds?: number; jobType?: string; job_type?: string; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs/lease`, { tenant_id: tenantId, lease_owner_id: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), lease_seconds: options.leaseSeconds ?? options.lease_seconds, job_type: clientString(options, "jobType", "job_type"), api_key_id: clientString(options, "apiKeyId", "api_key_id"), request_id: clientString(options, "requestId", "request_id") });
    return envelope("worker_job_lease", body);
  }

  async heartbeatWorkerJobHttp(tenantId: string, projectId: string, jobId: string, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; leaseSeconds?: number; lease_seconds?: number; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs/${encodeURIComponent(jobId)}/heartbeat`, { tenant_id: tenantId, lease_owner_id: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), lease_seconds: options.leaseSeconds ?? options.lease_seconds, api_key_id: clientString(options, "apiKeyId", "api_key_id"), request_id: clientString(options, "requestId", "request_id") });
    return envelope("worker_job_heartbeat", body);
  }

  async completeWorkerJobHttp(tenantId: string, projectId: string, jobId: string, result: JsonRecord = {}, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs/${encodeURIComponent(jobId)}/complete`, { tenant_id: tenantId, result, lease_owner_id: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), api_key_id: clientString(options, "apiKeyId", "api_key_id"), request_id: clientString(options, "requestId", "request_id") });
    return envelope("worker_job_complete", body);
  }

  async failWorkerJobHttp(tenantId: string, projectId: string, jobId: string, error: JsonRecord = {}, options: SaaSClientOptions & { leaseOwnerId?: string; lease_owner_id?: string; retryAfterSeconds?: number; retry_after_seconds?: number; apiKeyId?: string; api_key_id?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs/${encodeURIComponent(jobId)}/fail`, { tenant_id: tenantId, error, lease_owner_id: clientRequiredString(options, "leaseOwnerId", "lease_owner_id"), retry_after_seconds: options.retryAfterSeconds ?? options.retry_after_seconds, api_key_id: clientString(options, "apiKeyId", "api_key_id"), request_id: clientString(options, "requestId", "request_id") });
    return envelope("worker_job_fail", body);
  }

  async listWorkerJobsHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { status?: string; jobType?: string; job_type?: string; limit?: number; authKeyId?: string; auth_key_id?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/worker-jobs`, { tenant_id: tenantId, status: clientString(options, "status"), job_type: clientString(options, "jobType", "job_type"), limit: options.limit, auth_key_id: clientString(options, "authKeyId", "auth_key_id") });
    return envelope("worker_jobs", body);
  }

  async createApiKeyHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { name: string; scopes: string[] } & { keyId?: string; authKeyId?: string; revealSecret?: boolean; apiKey?: string }): Promise<SaaSClientEnvelope<SaaSApiKeyCreateResult, "create_api_key">> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { tenant_id: tenantId, name: String(options.name), scopes: arrayOfStrings(options.scopes), key_id: clientString(options, "keyId", "key_id"), auth_key_id: clientString(options, "authKeyId", "auth_key_id"), reveal_secret: clientBool(options, "revealSecret", "reveal_secret") });
    return envelope("create_api_key", body as SaaSApiKeyCreateResult);
  }

  async listApiKeysHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string; apiKey?: string; api_key?: string } = {}): Promise<SaaSClientEnvelope<SaaSApiKeyListResult, "list_api_keys">> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { tenant_id: tenantId, auth_key_id: clientString(options, "authKeyId", "auth_key_id") });
    return envelope("list_api_keys", body as SaaSApiKeyListResult);
  }

  async verifyApiKeySecretHttp(tenantId: string, projectId: string, options: { keyId: string; secret: string; scope?: string }): Promise<SaaSClientEnvelope<SaaSApiKeyVerificationResult, "verify_api_key_secret">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(options.keyId)}/verify`, { tenant_id: tenantId, secret: options.secret, scope: options.scope });
    return envelope("verify_api_key_secret", body as SaaSApiKeyVerificationResult);
  }

  async revokeApiKeyHttp(tenantId: string, projectId: string, keyId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string; apiKey?: string; api_key?: string } = {}): Promise<SaaSClientEnvelope<SaaSApiKeyRecord, "revoke_api_key">> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(keyId)}/revoke`, { tenant_id: tenantId, auth_key_id: clientString(options, "authKeyId", "auth_key_id") });
    return envelope("revoke_api_key", body as SaaSApiKeyRecord);
  }

  async configureApiKeyRateLimitHttp(tenantId: string, projectId: string, options: { keyId: string; operation: string; limit: number; period?: string; authKeyId?: string }): Promise<SaaSClientEnvelope<SaaSApiKeyRateLimit, "configure_api_key_rate_limit">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(options.keyId)}/rate-limit`, { tenant_id: tenantId, operation: options.operation, limit: options.limit, period: options.period, auth_key_id: options.authKeyId });
    return envelope("configure_api_key_rate_limit", body as SaaSApiKeyRateLimit);
  }

  async apiKeyRateLimitSnapshotHttp(tenantId: string, projectId: string, options: { keyId?: string } = {}): Promise<SaaSClientEnvelope<SaaSApiKeyRateLimitSnapshot, "api_key_rate_limit_snapshot">> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/rate-limits`, { tenant_id: tenantId, key_id: options.keyId });
    return envelope("api_key_rate_limit_snapshot", body as SaaSApiKeyRateLimitSnapshot);
  }

  async sdkSubmitHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { datasetId?: string; dataset_id?: string; agentRef?: string; agent_ref?: string; metadata?: JsonRecord; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string }): Promise<JsonRecord> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/sdk-submit`, { tenant_id: tenantId, dataset_id: clientRequiredString(options, "datasetId", "dataset_id"), agent_ref: clientRequiredString(options, "agentRef", "agent_ref"), run_id: clientString(options, "runId", "run_id"), metadata: { client: SAAS_CLIENT_VERSION, ...(options.metadata ?? {}) }, api_key_id: clientString(options, "apiKeyId", "api_key_id"), idempotency_key: clientString(options, "idempotencyKey", "idempotency_key"), request_id: clientString(options, "requestId", "request_id") }, clientAuthHeaders(options));
    return envelope("sdk_submit", body);
  }

  async uploadRunHttp(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: SaaSClientOptions & { uploadId?: string; upload_id?: string; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string } = {}): Promise<JsonRecord> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const upload = clientUploadOptions(options);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/upload`, { tenant_id: tenantId, result, upload_id: upload.uploadId, api_key_id: upload.apiKeyId, idempotency_key: upload.idempotencyKey, request_id: upload.requestId }, clientAuthHeaders(options));
    return envelope("upload_run", body);
  }

  async ingestTraceHttp(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: SaaSClientOptions & { batchId?: string; batch_id?: string; apiKeyId?: string; api_key_id?: string; apiKey?: string; idempotencyKey?: string; idempotency_key?: string; requestId?: string; request_id?: string } = {}): Promise<SaaSClientEnvelope<SaaSTraceIngestResult, "ingest_trace">> {
    rejectRawApiKey(clientString(options, "apiKey", "api_key"));
    const trace = clientTraceOptions(options);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/trace-events`, { tenant_id: tenantId, observations, batch_id: trace.batchId, api_key_id: trace.apiKeyId, idempotency_key: trace.idempotencyKey, request_id: trace.requestId }, clientAuthHeaders(options));
    return envelope("ingest_trace", body as SaaSTraceIngestResult);
  }

  async lifecycleHttp(tenantId: string, projectId: string, runId: string): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/lifecycle`, { tenant_id: tenantId });
    return envelope("lifecycle_snapshot", body);
  }

  async usageHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/usage`, { tenant_id: tenantId, auth_key_id: clientString(options, "authKeyId", "auth_key_id") }, clientAuthHeaders(options));
    return envelope("usage_snapshot", body);
  }

  async usageSnapshotHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): Promise<JsonRecord> {
    return this.usageHttp(tenantId, projectId, options);
  }

  async quotaSnapshotHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): Promise<SaaSClientEnvelope<SaaSQuotaSnapshotResult, "quota_snapshot">> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/quota`, { tenant_id: tenantId, auth_key_id: clientString(options, "authKeyId", "auth_key_id") }, clientAuthHeaders(options));
    return envelope("quota_snapshot", body as SaaSQuotaSnapshotResult);
  }

  async billingCheckoutPlanHttp(tenantId: string, projectId: string, options: SaaSBillingCheckoutOptions): Promise<SaaSClientEnvelope<SaaSBillingCheckoutPlan, "billing_checkout_plan">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/billing/checkout-plan`, {
      tenant_id: tenantId,
      project_id: projectId,
      customer_ref: options.customerRef,
      price: options.price,
      success_url: options.successUrl,
      cancel_url: options.cancelUrl,
      provider_config: options.providerConfig,
      usage_rollup: options.usageRollup ?? {},
      metadata: options.metadata ?? {},
      idempotency_key: options.idempotencyKey,
      auth_key_id: clientString(options, "authKeyId", "auth_key_id"),
    }, clientAuthHeaders(options));
    return envelope("billing_checkout_plan", body as SaaSBillingCheckoutPlan);
  }

  async billingPortalPlanHttp(tenantId: string, projectId: string, options: SaaSBillingPortalOptions): Promise<SaaSClientEnvelope<SaaSBillingPortalPlan, "billing_portal_plan">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/billing/portal-plan`, {
      tenant_id: tenantId,
      project_id: projectId,
      customer_ref: options.customerRef,
      return_url: options.returnUrl,
      provider_config: options.providerConfig,
      idempotency_key: options.idempotencyKey,
      auth_key_id: clientString(options, "authKeyId", "auth_key_id"),
    }, clientAuthHeaders(options));
    return envelope("billing_portal_plan", body as SaaSBillingPortalPlan);
  }

  async billingWebhookIngestHttp(tenantId: string, projectId: string, options: SaaSBillingWebhookOptions): Promise<SaaSClientEnvelope<SaaSBillingWebhookIngestResult, "billing_webhook_ingest">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/billing/webhooks/ingest`, {
      tenant_id: tenantId,
      project_id: projectId,
      provider: options.provider,
      mode: options.mode,
      event_type: options.eventType,
      event_id: options.eventId,
      payload_sha256: options.payloadSha256,
      signature_header_present: options.signatureHeaderPresent,
      webhook_secret_ref: options.webhookSecretRef,
      livemode: options.livemode,
      customer_ref: options.customerRef,
      amount_minor: options.amountMinor,
      currency: options.currency,
      invoice_ref: options.invoiceRef,
      usage_units: options.usageUnits,
      metadata: options.metadata ?? {},
      auth_key_id: clientString(options, "authKeyId", "auth_key_id"),
    }, clientAuthHeaders(options));
    return envelope("billing_webhook_ingest", body as SaaSBillingWebhookIngestResult);
  }

  async configureOauthProviderHttp(tenantId: string, projectId: string, options: SaaSOAuthProviderConfigureOptions): Promise<SaaSClientEnvelope<SaaSOAuthProviderConfig, "configure_oauth_provider">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/commercial-auth-payment/oauth-providers/configure`, {
      tenant_id: tenantId,
      provider: options.provider,
      client_id_ref: options.clientIdRef,
      client_secret_ref: options.clientSecretRef,
      redirect_uris: options.redirectUris,
      scopes: options.scopes,
      config_id: options.configId,
      auth_key_id: options.authKeyId,
    });
    return envelope("configure_oauth_provider", body as SaaSOAuthProviderConfig);
  }

  async beginOauthAuthorizationHttp(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationBeginOptions): Promise<SaaSClientEnvelope<SaaSOAuthAuthorizationBeginResult, "oauth_authorization_begin">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/commercial-auth-payment/oauth-authorizations/begin`, {
      tenant_id: tenantId,
      provider_config_id: options.providerConfigId,
      redirect_uri: options.redirectUri,
      code_verifier: options.codeVerifier,
      state: options.state,
      auth_key_id: options.authKeyId,
    });
    return envelope("oauth_authorization_begin", body as SaaSOAuthAuthorizationBeginResult);
  }

  async completeOauthAuthorizationHttp(tenantId: string, projectId: string, options: SaaSOAuthAuthorizationCompleteOptions): Promise<SaaSClientEnvelope<SaaSOAuthAuthorizationCompleteResult, "oauth_authorization_complete">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/commercial-auth-payment/oauth-authorizations/${encodeURIComponent(options.flowId)}/complete`, {
      tenant_id: tenantId,
      state: options.state,
      code_verifier: options.codeVerifier,
      redirect_uri: options.redirectUri,
      subject_ref: options.subjectRef,
      provider_code_ref: options.providerCodeRef,
      provider_error: options.providerError,
      access_token_ref: options.accessTokenRef,
      refresh_token_ref: options.refreshTokenRef,
      session_id: options.sessionId,
      auth_key_id: options.authKeyId,
    });
    return envelope("oauth_authorization_complete", body as SaaSOAuthAuthorizationCompleteResult);
  }

  async billingLedgerHttp(tenantId: string, projectId: string, options: SaaSClientOptions & { authKeyId?: string; auth_key_id?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/billing/ledger`, { tenant_id: tenantId, auth_key_id: clientString(options, "authKeyId", "auth_key_id") }, clientAuthHeaders(options));
    return envelope("billing_ledger", body);
  }

  async auditLogHttp(tenantId: string, projectId: string, options: { runId?: string; actionPrefix?: string; authKeyId?: string; limit?: number } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/audit-log`, { tenant_id: tenantId, run_id: options.runId, action_prefix: options.actionPrefix, auth_key_id: options.authKeyId, limit: options.limit });
    return envelope("audit_log", body);
  }

  async verifyAuditChainHttp(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/audit-chain/verify`, { tenant_id: tenantId, auth_key_id: options.authKeyId, request_id: options.requestId });
    return envelope("audit_chain_verify", body);
  }

  async evaluateReleaseGateHttp(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-gate`, { tenant_id: tenantId, evaluator: options.evaluator, min_score: options.minScore, required_trace_completeness: options.requiredTraceCompleteness, auth_key_id: options.authKeyId, request_id: options.requestId });
    return envelope("release_gate", body);
  }

  async buildReleaseEvidencePacketHttp(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-evidence`, { tenant_id: tenantId, auth_key_id: options.authKeyId });
    return envelope("release_evidence", body);
  }

  async verifyReleaseEvidencePacketHttp(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-evidence/verify`, { tenant_id: tenantId, auth_key_id: options.authKeyId, packet: options.packet, request_id: options.requestId });
    return envelope("release_evidence_verify", body);
  }

  async createArtifactManifestHttp(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: SaaSClientOptions & { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): Promise<SaaSClientEnvelope<SaaSArtifactManifestResult, "artifact_manifest">> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/artifact-manifests`, { tenant_id: tenantId, manifest, artifact_id: options.artifactId, api_key_id: options.apiKeyId, idempotency_key: options.idempotencyKey, request_id: options.requestId }, clientAuthHeaders(options));
    return envelope("artifact_manifest", body as SaaSArtifactManifestResult);
  }

  async listArtifactManifestsHttp(tenantId: string, projectId: string, runId: string, options: SaaSClientOptions & { authKeyId?: string } = {}): Promise<SaaSClientEnvelope<SaaSArtifactManifestListResult, "artifact_manifests">> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/artifact-manifests`, { tenant_id: tenantId, auth_key_id: options.authKeyId }, clientAuthHeaders(options));
    return envelope("artifact_manifests", body as SaaSArtifactManifestListResult);
  }
}
export const snapshotSaaSControlPlane = (service: SaaSControlPlaneService): SaaSControlPlaneState => service.snapshotState();
export const writeSaaSControlPlaneState = (service: SaaSControlPlaneService, outputPath: string): Promise<string> => service.writeState(outputPath);
export const saasControlPlaneFromState = (payload: unknown): SaaSControlPlaneService => SaaSControlPlaneService.fromState(payload);
export const saasControlPlaneFromStateFile = (inputPath: string): Promise<SaaSControlPlaneService> => SaaSControlPlaneService.fromStateFile(inputPath);

type CliOptions = Record<string, string | boolean | string[]>;

const SAAS_CLI_COMMANDS = new Set(["bootstrap", "api-key-create", "api-key-list", "api-key-verify", "api-key-revoke", "api-key-rate-limit", "api-key-rate-limits", "oauth-connect-start", "oauth-connection", "oauth-disconnect", "sdk-submit", "run-upload", "trace-ingest", "lifecycle", "quota", "usage", "billing-checkout-plan", "billing-portal-plan", "billing-webhook-ingest", "billing-ledger", "oauth-provider-configure", "oauth-authorization-begin", "oauth-authorization-complete", "artifact-manifest-create", "artifact-manifest-list", "release-gate", "audit-log", "audit-chain-verify", "release-evidence", "release-evidence-verify", "job-enqueue", "job-lease", "job-heartbeat", "job-complete", "job-fail", "job-list", "state"]);

export async function runSaaSCli(argv: string[] = process.argv.slice(2)): Promise<JsonRecord> {
  const commandIndex = argv.findIndex((arg) => SAAS_CLI_COMMANDS.has(arg));
  const command = commandIndex >= 0 ? argv[commandIndex] : "state";
  const options = parseCliArgs(commandIndex >= 0 ? [...argv.slice(0, commandIndex), ...argv.slice(commandIndex + 1)] : argv);
  if (options.help || options.h) {
    return { operation: "help", usage: saasCliUsage() };
  }
  const baseUrl = stringOption(options, "base-url", false);
  const stateInput = stringOption(options, "state-input", false);
  const stateOutput = stringOption(options, "state-output", false);
  if (baseUrl !== undefined && stateInput !== undefined) throw new SecretInputError("--base-url cannot be combined with --state-input");
  if (baseUrl !== undefined && stateOutput !== undefined) throw new SecretInputError("--base-url cannot be combined with --state-output");
  const client = baseUrl !== undefined ? SaaSIngestionClient.forBaseUrl(baseUrl) : (stateInput !== undefined ? await SaaSIngestionClient.fromStateFile(stateInput) : new SaaSIngestionClient());
  let result: JsonRecord;
  switch (command) {
    case "bootstrap":
      result = baseUrl !== undefined
        ? await client.bootstrapProjectHttp({ tenantName: stringOption(options, "tenant-name", true), projectName: stringOption(options, "project-name", true), tenantId: stringOption(options, "tenant-id", false), projectId: stringOption(options, "project-id", false), datasetId: stringOption(options, "dataset-id", false), datasetName: stringOption(options, "dataset-name", false) })
        : client.bootstrapProject({ tenantName: stringOption(options, "tenant-name", true), projectName: stringOption(options, "project-name", true), tenantId: stringOption(options, "tenant-id", false), projectId: stringOption(options, "project-id", false), datasetId: stringOption(options, "dataset-id", false), datasetName: stringOption(options, "dataset-name", false) });
      break;
    case "api-key-create":
      result = baseUrl !== undefined
        ? await client.createApiKeyHttp(projectTenant(options).tenantId, projectTenant(options).projectId, {
          name: stringOption(options, "name", true), scopes: stringListOption(options, "scope", true), keyId: stringOption(options, "key-id", false), authKeyId: stringOption(options, "auth-key-id", false), revealSecret: Boolean(options["reveal-secret"]),
        })
        : client.createApiKey(projectTenant(options).tenantId, projectTenant(options).projectId, {
          name: stringOption(options, "name", true), scopes: stringListOption(options, "scope", true), keyId: stringOption(options, "key-id", false), authKeyId: stringOption(options, "auth-key-id", false), revealSecret: Boolean(options["reveal-secret"]),
        });
      break;
    case "api-key-list":
      result = baseUrl !== undefined
        ? await client.listApiKeysHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.listApiKeys(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "api-key-verify":
      result = baseUrl !== undefined
        ? await client.verifyApiKeySecretHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), secret: stringOption(options, "secret", true), scope: stringOption(options, "scope", false) })
        : client.verifyApiKeySecret(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), secret: stringOption(options, "secret", true), scope: stringOption(options, "scope", false) });
      break;
    case "api-key-revoke":
      result = baseUrl !== undefined
        ? await client.revokeApiKeyHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "key-id", true), { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.revokeApiKey(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "key-id", true), { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "api-key-rate-limit":
      result = baseUrl !== undefined
        ? await client.configureApiKeyRateLimitHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), operation: stringOption(options, "operation", true), limit: numberOption(options, "limit", true), period: stringOption(options, "period", false), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.configureApiKeyRateLimit(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), operation: stringOption(options, "operation", true), limit: numberOption(options, "limit", true), period: stringOption(options, "period", false), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "api-key-rate-limits":
      result = baseUrl !== undefined
        ? await client.apiKeyRateLimitSnapshotHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", false) })
        : client.apiKeyRateLimitSnapshot(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", false) });
      break;
    case "oauth-connect-start":
      {
        const connectionClient = hostedAccountConnectionClient(baseUrl, stateInput, stateOutput);
        const provider = normalizeAccountConnectionProvider(stringOption(options, "provider", true));
        const binding = accountConnectionBindingOptions(options, provider);
        const payload = await connectionClient.start(binding);
        assertPublicAccountConnectionPayload(payload);
        result = parseAccountConnectionStart(payload, {
          expectedProvider: provider,
          expectedGoogleAudience: stringOption(options, "expected-google-audience", false),
        }) as unknown as JsonRecord;
      }
      break;
    case "oauth-connection":
      {
        const connectionClient = hostedAccountConnectionClient(baseUrl, stateInput, stateOutput);
        const provider = normalizeAccountConnectionProvider(stringOption(options, "provider", true));
        const payload = await connectionClient.connection(accountConnectionBindingOptions(options, provider));
        assertPublicAccountConnectionPayload(payload);
        result = parseAccountConnection(payload, { expectedProvider: provider }) as unknown as JsonRecord;
      }
      break;
    case "oauth-disconnect":
      {
        const connectionClient = hostedAccountConnectionClient(baseUrl, stateInput, stateOutput);
        const provider = normalizeAccountConnectionProvider(stringOption(options, "provider", true));
        const payload = await connectionClient.disconnect(accountConnectionBindingOptions(options, provider));
        assertPublicAccountConnectionPayload(payload);
        result = parseAccountConnectionDisconnect(payload, { expectedProvider: provider }) as unknown as JsonRecord;
      }
      break;
    case "sdk-submit":
      result = baseUrl !== undefined
        ? await client.sdkSubmitHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { datasetId: stringOption(options, "dataset-id", true), agentRef: stringOption(options, "agent-ref", true), runId: stringOption(options, "run-id", false), metadata: await jsonObjectOption(options, "metadata", {}), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) })
        : client.sdkSubmit(projectTenant(options).tenantId, projectTenant(options).projectId, { datasetId: stringOption(options, "dataset-id", true), agentRef: stringOption(options, "agent-ref", true), runId: stringOption(options, "run-id", false), metadata: await jsonObjectOption(options, "metadata", {}), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "run-upload":
      {
        const resultPayload = await jsonObjectOption(options, "result", {});
        result = baseUrl !== undefined
          ? await client.uploadRunHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), resultPayload, { uploadId: stringOption(options, "upload-id", false), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) })
          : client.uploadRun(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), resultPayload, { uploadId: stringOption(options, "upload-id", false), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) });
      }
      break;
    case "trace-ingest":
      result = baseUrl !== undefined
        ? await client.ingestTraceHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), await jsonArrayOption(options, "observations"), { batchId: stringOption(options, "batch-id", false), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) })
        : client.ingestTrace(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), await jsonArrayOption(options, "observations"), { batchId: stringOption(options, "batch-id", false), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "lifecycle":
      result = baseUrl !== undefined
        ? await client.lifecycleHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true))
        : client.lifecycle(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true));
      break;
    case "quota":
      result = baseUrl !== undefined ? await client.quotaSnapshotHttp(projectTenant(options).tenantId, projectTenant(options).projectId) : client.quotaSnapshot(projectTenant(options).tenantId, projectTenant(options).projectId);
      break;
    case "usage":
      result = baseUrl !== undefined
        ? await client.usageHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.usage(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "billing-checkout-plan":
      result = baseUrl !== undefined
        ? await client.billingCheckoutPlanHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { customerRef: stringOption(options, "customer-ref", true), price: await jsonObjectOption(options, "price", {}), successUrl: stringOption(options, "success-url", true), cancelUrl: stringOption(options, "cancel-url", true), providerConfig: await optionalJsonObjectOption(options, "provider-config"), usageRollup: await jsonObjectOption(options, "usage-rollup", {}), metadata: await jsonObjectOption(options, "metadata", {}), idempotencyKey: stringOption(options, "idempotency-key", false), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.billingCheckoutPlan(projectTenant(options).tenantId, projectTenant(options).projectId, { customerRef: stringOption(options, "customer-ref", true), price: await jsonObjectOption(options, "price", {}), successUrl: stringOption(options, "success-url", true), cancelUrl: stringOption(options, "cancel-url", true), providerConfig: await optionalJsonObjectOption(options, "provider-config"), usageRollup: await jsonObjectOption(options, "usage-rollup", {}), metadata: await jsonObjectOption(options, "metadata", {}), idempotencyKey: stringOption(options, "idempotency-key", false), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "billing-portal-plan":
      result = baseUrl !== undefined
        ? await client.billingPortalPlanHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { customerRef: stringOption(options, "customer-ref", true), returnUrl: stringOption(options, "return-url", true), providerConfig: await optionalJsonObjectOption(options, "provider-config"), idempotencyKey: stringOption(options, "idempotency-key", false), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.billingPortalPlan(projectTenant(options).tenantId, projectTenant(options).projectId, { customerRef: stringOption(options, "customer-ref", true), returnUrl: stringOption(options, "return-url", true), providerConfig: await optionalJsonObjectOption(options, "provider-config"), idempotencyKey: stringOption(options, "idempotency-key", false), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "billing-webhook-ingest":
      result = baseUrl !== undefined
        ? await client.billingWebhookIngestHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { provider: stringOption(options, "provider", true), mode: stringOption(options, "mode", true), eventType: stringOption(options, "event-type", true), eventId: stringOption(options, "event-id", true), payloadSha256: stringOption(options, "payload-sha256", true), signatureHeaderPresent: Boolean(options["signature-header-present"]), webhookSecretRef: stringOption(options, "webhook-secret-ref", false), livemode: Boolean(options.livemode), customerRef: stringOption(options, "customer-ref", false), amountMinor: optionalNumberOption(options, "amount-minor"), currency: stringOption(options, "currency", false), invoiceRef: stringOption(options, "invoice-ref", false), usageUnits: optionalNumberOption(options, "usage-units"), metadata: await jsonObjectOption(options, "metadata", {}), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.billingWebhookIngest(projectTenant(options).tenantId, projectTenant(options).projectId, { provider: stringOption(options, "provider", true), mode: stringOption(options, "mode", true), eventType: stringOption(options, "event-type", true), eventId: stringOption(options, "event-id", true), payloadSha256: stringOption(options, "payload-sha256", true), signatureHeaderPresent: Boolean(options["signature-header-present"]), webhookSecretRef: stringOption(options, "webhook-secret-ref", false), livemode: Boolean(options.livemode), customerRef: stringOption(options, "customer-ref", false), amountMinor: optionalNumberOption(options, "amount-minor"), currency: stringOption(options, "currency", false), invoiceRef: stringOption(options, "invoice-ref", false), usageUnits: optionalNumberOption(options, "usage-units"), metadata: await jsonObjectOption(options, "metadata", {}), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "billing-ledger":
      result = baseUrl !== undefined
        ? await client.billingLedgerHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.billingLedger(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "oauth-provider-configure":
      {
        const oauthOptions: SaaSOAuthProviderConfigureOptions = {
          provider: stringOption(options, "provider", true),
          clientIdRef: stringOption(options, "client-id-ref", true),
          clientSecretRef: stringOption(options, "client-secret-ref", true),
          redirectUris: stringListOption(options, "redirect-uri", true),
          scopes: stringListOption(options, "scope", true),
          configId: stringOption(options, "config-id", false),
          authKeyId: stringOption(options, "auth-key-id", false),
        };
        result = baseUrl !== undefined
          ? await client.configureOauthProviderHttp(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions)
          : client.configureOauthProvider(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions);
      }
      break;
    case "oauth-authorization-begin":
      {
        const oauthOptions: SaaSOAuthAuthorizationBeginOptions = {
          providerConfigId: stringOption(options, "provider-config-id", true),
          redirectUri: stringOption(options, "redirect-uri", true),
          codeVerifier: stringOption(options, "code-verifier", true),
          state: stringOption(options, "state", false),
          authKeyId: stringOption(options, "auth-key-id", false),
        };
        result = baseUrl !== undefined
          ? await client.beginOauthAuthorizationHttp(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions)
          : client.beginOauthAuthorization(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions);
      }
      break;
    case "oauth-authorization-complete":
      {
        const oauthOptions: SaaSOAuthAuthorizationCompleteOptions = {
          flowId: stringOption(options, "flow-id", true),
          state: stringOption(options, "state", true),
          codeVerifier: stringOption(options, "code-verifier", true),
          redirectUri: stringOption(options, "redirect-uri", true),
          subjectRef: stringOption(options, "subject-ref", true),
          providerCodeRef: stringOption(options, "provider-code-ref", false),
          providerError: stringOption(options, "provider-error", false),
          accessTokenRef: stringOption(options, "access-token-ref", false),
          refreshTokenRef: stringOption(options, "refresh-token-ref", false),
          sessionId: stringOption(options, "session-id", false),
          authKeyId: stringOption(options, "auth-key-id", false),
        };
        result = baseUrl !== undefined
          ? await client.completeOauthAuthorizationHttp(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions)
          : client.completeOauthAuthorization(projectTenant(options).tenantId, projectTenant(options).projectId, oauthOptions);
      }
      break;
    case "release-gate":
      result = baseUrl !== undefined
        ? await client.evaluateReleaseGateHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { evaluator: stringOption(options, "evaluator", false), minScore: optionalNumberOption(options, "min-score"), requiredTraceCompleteness: optionalNumberOption(options, "required-trace-completeness"), authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.evaluateReleaseGate(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { evaluator: stringOption(options, "evaluator", false), minScore: optionalNumberOption(options, "min-score"), requiredTraceCompleteness: optionalNumberOption(options, "required-trace-completeness"), authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "audit-log":
      result = baseUrl !== undefined
        ? await client.auditLogHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { runId: stringOption(options, "run-id", false), actionPrefix: stringOption(options, "action-prefix", false), authKeyId: stringOption(options, "auth-key-id", false), limit: optionalNumberOption(options, "limit") })
        : client.auditLog(projectTenant(options).tenantId, projectTenant(options).projectId, { runId: stringOption(options, "run-id", false), actionPrefix: stringOption(options, "action-prefix", false), authKeyId: stringOption(options, "auth-key-id", false), limit: optionalNumberOption(options, "limit") });
      break;
    case "audit-chain-verify":
      result = baseUrl !== undefined
        ? await client.verifyAuditChainHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.verifyAuditChain(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "release-evidence":
      result = baseUrl !== undefined
        ? await client.buildReleaseEvidencePacketHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.buildReleaseEvidencePacket(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "release-evidence-verify":
      {
        const packet = await packetOption(options);
      result = baseUrl !== undefined
        ? await client.verifyReleaseEvidencePacketHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false), packet, requestId: stringOption(options, "request-id", false) })
        : client.verifyReleaseEvidencePacket(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false), packet, requestId: stringOption(options, "request-id", false) });
      }
      break;
    case "job-enqueue":
      {
        const payload = await jsonObjectOption(options, "payload", {});
        result = baseUrl !== undefined
          ? await client.enqueueWorkerJobHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { jobType: stringOption(options, "job-type", true), targetId: stringOption(options, "target-id", false), payload, jobId: stringOption(options, "job-id", false), priority: optionalNumberOption(options, "priority"), maxAttempts: optionalNumberOption(options, "max-attempts"), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) })
          : client.enqueueWorkerJob(projectTenant(options).tenantId, projectTenant(options).projectId, { jobType: stringOption(options, "job-type", true), targetId: stringOption(options, "target-id", false), payload, jobId: stringOption(options, "job-id", false), priority: optionalNumberOption(options, "priority"), maxAttempts: optionalNumberOption(options, "max-attempts"), apiKeyId: stringOption(options, "api-key-id", false), idempotencyKey: stringOption(options, "idempotency-key", false), requestId: stringOption(options, "request-id", false) });
      }
      break;
    case "job-lease":
      result = baseUrl !== undefined
        ? await client.leaseWorkerJobHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { leaseOwnerId: stringOption(options, "lease-owner-id", true), leaseSeconds: optionalNumberOption(options, "lease-seconds"), jobType: stringOption(options, "job-type", false), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.leaseWorkerJob(projectTenant(options).tenantId, projectTenant(options).projectId, { leaseOwnerId: stringOption(options, "lease-owner-id", true), leaseSeconds: optionalNumberOption(options, "lease-seconds"), jobType: stringOption(options, "job-type", false), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "job-heartbeat":
      result = baseUrl !== undefined
        ? await client.heartbeatWorkerJobHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), { leaseOwnerId: stringOption(options, "lease-owner-id", true), leaseSeconds: optionalNumberOption(options, "lease-seconds"), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.heartbeatWorkerJob(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), { leaseOwnerId: stringOption(options, "lease-owner-id", true), leaseSeconds: optionalNumberOption(options, "lease-seconds"), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "job-complete":
      {
        const completeResult = await jsonObjectOption(options, "result", {});
        result = baseUrl !== undefined
          ? await client.completeWorkerJobHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), completeResult, { leaseOwnerId: stringOption(options, "lease-owner-id", true), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) })
          : client.completeWorkerJob(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), completeResult, { leaseOwnerId: stringOption(options, "lease-owner-id", true), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) });
      }
      break;
    case "job-fail":
      {
        const errorPayload = await jsonObjectOption(options, "error", {});
        result = baseUrl !== undefined
          ? await client.failWorkerJobHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), errorPayload, { leaseOwnerId: stringOption(options, "lease-owner-id", true), retryAfterSeconds: optionalNumberOption(options, "retry-after-seconds"), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) })
          : client.failWorkerJob(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "job-id", true), errorPayload, { leaseOwnerId: stringOption(options, "lease-owner-id", true), retryAfterSeconds: optionalNumberOption(options, "retry-after-seconds"), apiKeyId: stringOption(options, "api-key-id", false), requestId: stringOption(options, "request-id", false) });
      }
      break;
    case "job-list":
      result = baseUrl !== undefined
        ? await client.listWorkerJobsHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { status: stringOption(options, "status", false), jobType: stringOption(options, "job-type", false), limit: optionalNumberOption(options, "limit"), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.listWorkerJobs(projectTenant(options).tenantId, projectTenant(options).projectId, { status: stringOption(options, "status", false), jobType: stringOption(options, "job-type", false), limit: optionalNumberOption(options, "limit"), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    default:
      throw new SecretInputError(`unsupported command: ${command}`);
  }
  if (stateOutput !== undefined) result.state_output = await client.writeState(stateOutput);
  return result;
}

function parseCliArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) throw new SecretInputError(`unexpected argument: ${arg}`);
    const name = arg.slice(2);
    const next = args[index + 1];
    if (next === undefined || next.startsWith("--")) {
      options[name] = true;
      continue;
    }
    const current = options[name];
    if (current === undefined) options[name] = next;
    else if (Array.isArray(current)) current.push(next);
    else options[name] = [String(current), next];
    index += 1;
  }
  return options;
}

function stringOption(options: CliOptions, name: string, required: true): string;
function stringOption(options: CliOptions, name: string, required: false): string | undefined;
function stringOption(options: CliOptions, name: string, required: boolean): string | undefined {
  const value = options[name];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[value.length - 1];
  if (required) throw new SecretInputError(`missing required --${name}`);
  return undefined;
}

function stringListOption(options: CliOptions, name: string, required: true): string[];
function stringListOption(options: CliOptions, name: string, required: false): string[] | undefined;
function stringListOption(options: CliOptions, name: string, required: boolean): string[] | undefined {
  const value = options[name];
  const list = Array.isArray(value) ? value.map(String) : (typeof value === "string" ? [value] : []);
  if (list.length === 0 && required) throw new SecretInputError(`missing required --${name}`);
  return list.length > 0 ? list : undefined;
}

function numberOption(options: CliOptions, name: string, required: boolean): number {
  const raw = options[name];
  const value = typeof raw === "string" ? raw : (Array.isArray(raw) ? raw[raw.length - 1] : undefined);
  if (value === undefined) throw new SecretInputError(`missing required --${name}`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new SecretInputError(`--${name} must be numeric`);
  return parsed;
}

function optionalNumberOption(options: CliOptions, name: string): number | undefined {
  const raw = options[name];
  const value = typeof raw === "string" ? raw : (Array.isArray(raw) ? raw[raw.length - 1] : undefined);
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new SecretInputError(`--${name} must be numeric`);
  return parsed;
}

async function packetOption(options: CliOptions): Promise<JsonRecord | undefined> {
  const packetJson = stringOption(options, "packet-json", false);
  const packetFile = stringOption(options, "packet-file", false);
  if (packetJson !== undefined && packetFile !== undefined) throw new SecretInputError("provide only one of --packet-json or --packet-file");
  if (packetJson !== undefined) {
    const parsed = JSON.parse(packetJson) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError("--packet-json must decode to an object");
    return parsed;
  }
  if (packetFile !== undefined) {
    assertPublicControlPlanePath(packetFile);
    const fs = await import("node:fs/promises");
    const parsed = JSON.parse(await fs.readFile(packetFile, "utf8")) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError("--packet-file must contain a JSON object");
    return parsed;
  }
  return undefined;
}

async function jsonObjectOption(options: CliOptions, name: string, defaultValue: JsonRecord): Promise<JsonRecord> {
  const jsonValue = stringOption(options, `${name}-json`, false);
  const fileValue = stringOption(options, `${name}-file`, false);
  if (jsonValue !== undefined && fileValue !== undefined) throw new SecretInputError(`provide only one of --${name}-json or --${name}-file`);
  if (jsonValue !== undefined) {
    const parsed = JSON.parse(jsonValue) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError(`--${name}-json must decode to an object`);
    return parsed;
  }
  if (fileValue !== undefined) {
    assertPublicControlPlanePath(fileValue);
    const fs = await import("node:fs/promises");
    const parsed = JSON.parse(await fs.readFile(fileValue, "utf8")) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError(`--${name}-file must contain a JSON object`);
    return parsed;
  }
  return defaultValue;
}

async function optionalJsonObjectOption(options: CliOptions, name: string): Promise<JsonRecord | undefined> {
  const hasJson = stringOption(options, `${name}-json`, false) !== undefined;
  const hasFile = stringOption(options, `${name}-file`, false) !== undefined;
  return hasJson || hasFile ? jsonObjectOption(options, name, {}) : undefined;
}

async function jsonArrayOption(options: CliOptions, name: string): Promise<JsonRecord[]> {
  const jsonValue = stringOption(options, `${name}-json`, false);
  const fileValue = stringOption(options, `${name}-file`, false);
  if (jsonValue !== undefined && fileValue !== undefined) throw new SecretInputError(`provide only one of --${name}-json or --${name}-file`);
  const raw = jsonValue ?? (fileValue !== undefined ? await (async () => {
    assertPublicControlPlanePath(fileValue);
    const fs = await import("node:fs/promises");
    return fs.readFile(fileValue, "utf8");
  })() : undefined);
  if (raw === undefined) return [];
  const parsed = JSON.parse(raw) as unknown;
  if (!Array.isArray(parsed) || parsed.some((item) => !isRecord(item))) throw new SecretInputError(`--${name}-json must decode to an array of objects`);
  return parsed as JsonRecord[];
}

function projectTenant(options: CliOptions): { tenantId: string; projectId: string } {
  return { tenantId: stringOption(options, "tenant-id", true), projectId: stringOption(options, "project-id", true) };
}

function accountConnectionBindingOptions(
  options: CliOptions,
  provider: "github" | "google",
): { provider: "github" | "google"; tenantId: string; projectId: string; accountId: string } {
  const project = projectTenant(options);
  return {
    provider,
    tenantId: project.tenantId,
    projectId: project.projectId,
    accountId: stringOption(options, "account-id", true),
  };
}

function hostedAccountConnectionClient(
  baseUrl: string | undefined,
  stateInput: string | undefined,
  stateOutput: string | undefined,
): AccountConnectionHttpClient {
  if (baseUrl === undefined || stateInput !== undefined || stateOutput !== undefined) {
    throw new SecretInputError("hosted account connection commands require --base-url and do not support local state files");
  }
  return new AccountConnectionHttpClient({ baseUrl });
}

function saasCliUsage(): string {
  return `usage: node dist/saas.js [--state-input PATH] [--state-output PATH] [--base-url URL] <${[...SAAS_CLI_COMMANDS].join("|")}> [options]`;
}

async function mainSaaSCli(): Promise<number> {
  try {
    process.stdout.write(`${JSON.stringify(await runSaaSCli(), null, 0)}\n`);
    return 0;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`saas ingestion cli error: ${message}\n`);
    return 2;
  }
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  void mainSaaSCli().then((code) => { process.exitCode = code; });
}


function envelope<T extends JsonRecord, O extends SaaSClientOperation>(operation: O, result: T): SaaSClientEnvelope<T, O> { return { schema_version: CONTROL_PLANE_SCHEMA_VERSION, client_version: SAAS_CLIENT_VERSION, operation, result: cloneJson(result) }; }

export function buildSafeMediaEnvelope(value: unknown, options: { parts?: unknown; metadata?: JsonRecord } = {}): SaaSMediaEnvelope {
  const input = coerceAgentInput(value, options);
  const failures = [...unsafeMediaInputFields(value), ...unsafeMediaEnvelopeFields(input)];
  if (failures.length > 0) {
    throw new SecretInputError(`unsafe media envelope fields are not accepted: ${failures.join(", ")}`);
  }
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION,
    agent_input_schema_version: AGENT_INPUT_SCHEMA_VERSION,
    text: input.text,
    parts: input.parts.map((part) => cloneJson(part) as AgentInputPart),
    metadata: cloneJson(input.metadata) as JsonRecord,
    raw_payload_included: false,
    secret_value_present: false,
  };
}

function unsafeMediaInputFields(value: unknown): string[] {
  if (!isRecord(value)) return [];
  const failures: string[] = [];
  for (const key of Object.keys(value)) {
    const normalizedKey = key.toLowerCase().replace(/-/g, "_");
    if (UNSAFE_MEDIA_ENVELOPE_KEYS.has(normalizedKey)) failures.push(key);
  }
  return failures;
}

function unsafeMediaEnvelopeFields(input: AgentInput): string[] {
  const failures: string[] = [];
  input.parts.forEach((part, index) => {
    if (!AGENT_INPUT_PART_TYPES.includes(part.type)) failures.push(`parts[${index}].type`);
    for (const key of Object.keys(part)) {
      const normalizedKey = key.toLowerCase().replace(/-/g, "_");
      if (UNSAFE_MEDIA_ENVELOPE_KEYS.has(normalizedKey)) failures.push(`parts[${index}].${key}`);
    }
    if (part.type !== "text" && part.url !== undefined && signedUrlLooksSensitive(String(part.url))) failures.push(`parts[${index}].url`);
  });
  for (const key of Object.keys(input.metadata)) {
    const normalizedKey = key.toLowerCase().replace(/-/g, "_");
    if (UNSAFE_MEDIA_ENVELOPE_KEYS.has(normalizedKey)) failures.push(`metadata.${key}`);
  }
  return failures;
}

const UNSAFE_MEDIA_ENVELOPE_KEYS = new Set(["api_key", "authorization", "bearer", "cookie", "set_cookie", "password", "token", "access_token", "refresh_token", "client_secret", "secret", "content", "data", "bytes", "base64", "raw_payload", "payload"]);

function signedUrlLooksSensitive(url: string): boolean {
  try {
    const parsed = new URL(url);
    return Array.from(parsed.searchParams.keys()).some((key) => {
      const normalized = key.toLowerCase().replace(/-/g, "_");
      return normalized.includes("token") || normalized.includes("sig") || normalized.includes("signature") || normalized.includes("secret") || normalized.includes("key");
    });
  } catch {
    return false;
  }
}

function rejectRawApiKey(value: unknown): void { if (value !== undefined && value !== null && String(value).trim() !== "") throw new SecretInputError("raw API key values are not accepted by the local SaaS client; pass apiKeyId/keyId handles only"); }
function clientString(options: JsonRecord, ...keys: string[]): string | undefined { for (const key of keys) { const value = options[key]; if (typeof value === "string" && value.trim() !== "") return value; } return undefined; }
function clientRequiredString(options: JsonRecord, ...keys: string[]): string { const value = clientString(options, ...keys); if (value === undefined) throw new ValidationError(`missing required option: ${keys.join("/")}`); return value; }
function clientBool(options: JsonRecord, ...keys: string[]): boolean { for (const key of keys) { if (options[key] !== undefined) return Boolean(options[key]); } return false; }
function bearerAuthorizationHeader(secret: string): string { return String(secret).trim().toLowerCase().startsWith("bearer ") ? String(secret).trim() : `Bearer ${String(secret).trim()}`; }
function clientAuthHeaders(options: SaaSClientOptions): { headers?: Record<string, string> } {
  const secret = clientString(options, "bearerApiKey", "bearer_api_key", "apiKeySecret", "api_key_secret");
  return secret === undefined ? {} : { headers: { Authorization: bearerAuthorizationHeader(secret) } };
}
function bearerSecretFromHeaders(headers: Record<string, string | string[] | undefined> | undefined): string | undefined {
  if (headers === undefined) return undefined;
  const value = headers.Authorization ?? headers.authorization;
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw !== "string") return undefined;
  const match = /^Bearer\s+(.+)$/i.exec(raw.trim());
  return match === null ? undefined : match[1].trim();
}
function clientUploadOptions(options: SaaSClientOptions): { uploadId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } { return { uploadId: clientString(options, "uploadId", "upload_id"), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), idempotencyKey: clientString(options, "idempotencyKey", "idempotency_key"), requestId: clientString(options, "requestId", "request_id") }; }
function clientTraceOptions(options: SaaSClientOptions): { batchId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } { return { batchId: clientString(options, "batchId", "batch_id"), apiKeyId: clientString(options, "apiKeyId", "api_key_id"), idempotencyKey: clientString(options, "idempotencyKey", "idempotency_key"), requestId: clientString(options, "requestId", "request_id") }; }
function assertPublicControlPlanePath(inputPath: string): void { const normalized = resolve(inputPath).replaceAll("\\", "/").toLowerCase(); for (const part of [".secrets", "private_refs"]) { if (normalized.includes("/" + part + "/") || normalized.endsWith("/" + part)) throw new SecretInputError("refusing to read or write control-plane state under " + part); } }
function positiveInt(value: number, name: string): number { if (!Number.isInteger(value) || value < 1) throw new ValidationError(`${name} must be a positive integer`); return value; }
function leaseExpiresAt(now: string, seconds: number): string { if (!Number.isFinite(seconds) || seconds <= 0) throw new ValidationError("lease_seconds must be positive"); return new Date(Date.parse(now) + seconds * 1000).toISOString().replace(".000Z", ".000Z"); }
function leaseExpired(value: unknown, now = utcNow()): boolean { if (typeof value !== "string" || value.trim() === "") return false; return Date.parse(value) <= Date.parse(now); }
function jobAvailableForLease(job: JsonRecord, now: string): boolean {
  if (job.status === "queued" || job.status === "retrying") return job.available_at === null || job.available_at === undefined || job.available_at === "" || leaseExpired(job.available_at, now);
  if (job.status === "leased") return leaseExpired(job.lease_expires_at, now);
  return false;
}
function requireWorkerJobLease(job: JsonRecord, leaseOwnerId: string): void {
  if (job.status !== "leased") throw new ValidationError("worker job is not leased");
  if (job.lease_owner_id !== leaseOwnerId) throw new ValidationError("worker job lease owner mismatch");
  if (leaseExpired(job.lease_expires_at)) throw new ValidationError("worker job lease expired");
}

function pathTenantParameters(extraPathName?: string): JsonRecord[] {
  const params: JsonRecord[] = [
    { name: "project_id", in: "path", required: true, schema: { type: "string" } },
    { name: "tenant_id", in: "query", required: false, schema: { type: "string" } },
  ];
  if (extraPathName !== undefined) params.splice(1, 0, { name: extraPathName, in: "path", required: true, schema: { type: "string" } });
  return params;
}

function publicApiKey(record: JsonRecord): SaaSApiKeyRecord {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    tenant_id: String(record.tenant_id),
    project_id: String(record.project_id),
    key_id: String(record.key_id),
    name: String(record.name),
    prefix: String(record.prefix),
    secret_hash_present: Boolean(record.secret_hash_sha256),
    secret_value_present: false,
    status: String(record.status),
    scopes: arrayOfStrings(record.scopes),
    created_at: record.created_at,
    revoked_at: record.revoked_at,
    last_used_at: record.last_used_at,
    one_time_secret_displayed: Boolean(record.one_time_secret_displayed),
    verify_mode: record.verify_mode ?? null,
  };
}

const SECRET_REF_PREFIXES = ["env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:"] as const;
const FORBIDDEN_PUBLIC_REF_MARKERS = ["secret=", "client_secret=", "access_token=", "refresh_token=", "bearer ", "-----begin", "sk_test_", "sk_live_", "rk_live_", "whsec_", "card[number]", "cvc"] as const;

function normalizeOauthProvider(provider: string): "github" | "google" {
  const normalized = String(provider).trim().toLowerCase().replaceAll("-", "_");
  if (normalized !== "github" && normalized !== "google") throw new ValidationError("oauth provider must be github or google");
  return normalized;
}

function validatePublicRef(refName: string, value: string | undefined): void {
  if (value === undefined || String(value).trim() === "") throw new ValidationError(`${refName} must not be empty`);
  const lower = String(value).toLowerCase();
  if (FORBIDDEN_PUBLIC_REF_MARKERS.some((marker) => lower.includes(marker))) {
    throw new ValidationError(`${refName} must be a public-safe reference, not raw sensitive material`);
  }
}

function validateSecretRef(refName: string, value: string | undefined): void {
  if (value === undefined || value === "") throw new ValidationError(`${refName} is required`);
  validatePublicRef(refName, value);
  if (!SECRET_REF_PREFIXES.some((prefix) => value.startsWith(prefix))) {
    throw new ValidationError(`${refName} must use a secret reference prefix: ${SECRET_REF_PREFIXES.join(", ")}`);
  }
}

function validateOauthState(state: string): void {
  validatePublicRef("oauth_state", state);
  if (state.length < 16) throw new ValidationError("oauth state must be at least 16 characters");
  if (state.length > 512) throw new ValidationError("oauth state must be at most 512 characters");
}

function pkceS256Challenge(codeVerifier: string): string {
  const verifier = String(codeVerifier || "");
  if (verifier.length < 43 || verifier.length > 128) throw new ValidationError("pkce code_verifier must be 43-128 characters");
  if (!/^[A-Za-z0-9._~-]+$/.test(verifier)) throw new ValidationError("pkce code_verifier must use unreserved URI characters");
  return createHash("sha256").update(verifier, "ascii").digest("base64url");
}

function publicOauthProviderConfig(record: JsonRecord): SaaSOAuthProviderConfig {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION,
    tenant_id: String(record.tenant_id),
    project_id: String(record.project_id),
    config_id: String(record.config_id),
    provider: normalizeOauthProvider(String(record.provider)),
    client_id_ref: String(record.client_id_ref),
    client_secret_ref: String(record.client_secret_ref),
    redirect_uris: arrayOfStrings(record.redirect_uris),
    scopes: arrayOfStrings(record.scopes),
    enabled: Boolean(record.enabled),
    secret_value_present: false,
    configured_by_api_key_id: record.configured_by_api_key_id ?? null,
    created_at: record.created_at ?? null,
    updated_at: record.updated_at ?? null,
  };
}

function publicOauthAuthorizationFlow(record: JsonRecord): SaaSOAuthAuthorizationFlow {
  const rawStatus = String(record.status);
  const status: SaaSOAuthAuthorizationStatus = rawStatus === "failed" || rawStatus === "completed" ? rawStatus : "pending";
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION,
    tenant_id: String(record.tenant_id),
    project_id: String(record.project_id),
    flow_id: String(record.flow_id),
    provider: String(record.provider),
    provider_config_id: String(record.provider_config_id),
    redirect_uri: String(record.redirect_uri),
    state_hash_present: typeof record.state_hash_sha256 === "string" && record.state_hash_sha256 !== "",
    code_challenge: String(record.code_challenge),
    code_challenge_method: "S256",
    status,
    session_id: typeof record.session_id === "string" ? record.session_id : null,
    provider_code_ref_present: typeof record.provider_code_ref_sha256 === "string" && record.provider_code_ref_sha256 !== "",
    failure_reasons: arrayOfStrings(record.failure_reasons),
    secret_value_present: false,
    raw_code_present: false,
    raw_state_present: false,
    created_at: record.created_at ?? null,
    completed_at: record.completed_at ?? null,
  };
}

function publicOauthSession(record: JsonRecord): SaaSOAuthSession {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION,
    tenant_id: String(record.tenant_id),
    project_id: String(record.project_id),
    session_id: String(record.session_id),
    provider: normalizeOauthProvider(String(record.provider)),
    provider_config_id: String(record.provider_config_id),
    subject_ref: String(record.subject_ref),
    access_token_ref_present: typeof record.access_token_ref === "string" && record.access_token_ref !== "",
    refresh_token_ref_present: typeof record.refresh_token_ref === "string" && record.refresh_token_ref !== "",
    status: "active",
    secret_value_present: false,
    created_by_api_key_id: record.created_by_api_key_id ?? null,
    created_at: record.created_at ?? null,
    revoked_at: record.revoked_at ?? null,
  };
}

function normalizeScope(scope: string): string {
  const parsed = String(scope).trim();
  if (!parsed) throw new ValidationError("required scope must not be empty");
  return parsed;
}

function scopeAllows(grantedScopes: unknown, requiredScope: string): boolean {
  const granted = new Set((Array.isArray(grantedScopes) ? grantedScopes : []).map((scope) => String(scope).trim()).filter(Boolean));
  const expanded = new Set(granted);
  for (const scope of granted) {
    for (const item of SCOPE_ALIASES[scope] ?? []) expanded.add(item);
  }
  if (expanded.has("*") || expanded.has(ADMIN_ALL_SCOPE) || expanded.has(requiredScope)) return true;
  for (const scope of expanded) {
    if (scope.endsWith(":*") && requiredScope.startsWith(`${scope.slice(0, -2)}:`)) return true;
  }
  return false;
}

function idempotencyRecordKey(tenantId: string, projectId: string, operation: string, idempotencyKey: string): string {
  return sha256(`${tenantId}:${projectId}:${operation}:${idempotencyKey}`);
}

function apiKeyRateKey(tenantId: string, projectId: string, keyId: string, operation: string, period: string): string {
  return sha256(`${tenantId}:${projectId}:${keyId}:${operation}:${period}`);
}

function auditEventHash(event: JsonRecord): string {
  const payload = cloneJson(event) as JsonRecord;
  delete payload.audit_event_sha256;
  return sha256(JSON.stringify(sortJson(payload)));
}

function auditEventsInChainOrder(events: JsonRecord[]): JsonRecord[] {
  return events
    .map((event) => cloneJson(event) as JsonRecord)
    .sort((left, right) => {
      const position = Number(left.chain_position ?? 0) - Number(right.chain_position ?? 0);
      if (position !== 0) return position;
      const created = String(left.created_at ?? "").localeCompare(String(right.created_at ?? ""));
      if (created !== 0) return created;
      return String(left.audit_event_id ?? "").localeCompare(String(right.audit_event_id ?? ""));
    });
}

function auditChainTail(events: JsonRecord[], tenantId: string, projectId: string): JsonRecord | null {
  const ordered = auditEventsInChainOrder(events.filter((event) => event.tenant_id === tenantId && event.project_id === projectId));
  return ordered.length > 0 ? ordered[ordered.length - 1] : null;
}

export function verifyAuditHashChain(events: JsonRecord[]): JsonRecord {
  const ordered = auditEventsInChainOrder(events);
  let previousHash: string | null = null;
  let previousId: string | null = null;
  const failures: JsonRecord[] = [];
  ordered.forEach((event, index) => {
    const eventId = String(event.audit_event_id ?? "");
    const expectedHash = auditEventHash(event);
    if (event.audit_event_sha256 !== expectedHash) failures.push({ audit_event_id: eventId, reason: "event_hash_mismatch" });
    if ((event.previous_audit_event_id ?? null) !== previousId) failures.push({ audit_event_id: eventId, reason: "previous_event_id_mismatch" });
    if ((event.previous_audit_event_sha256 ?? null) !== previousHash) failures.push({ audit_event_id: eventId, reason: "previous_event_hash_mismatch" });
    if (Number(event.chain_position ?? -1) !== index) failures.push({ audit_event_id: eventId, reason: "chain_position_mismatch" });
    previousHash = String(event.audit_event_sha256 ?? expectedHash);
    previousId = eventId;
  });
  return {
    verified: failures.length === 0,
    event_count: ordered.length,
    head_audit_event_id: ordered[0]?.audit_event_id ?? null,
    head_audit_event_sha256: ordered[0]?.audit_event_sha256 ?? null,
    tail_audit_event_id: ordered[ordered.length - 1]?.audit_event_id ?? null,
    tail_audit_event_sha256: ordered[ordered.length - 1]?.audit_event_sha256 ?? null,
    failures,
  };
}

export function verifyReleaseEvidencePacket(packet: JsonRecord): JsonRecord {
  const payload = cloneJson(packet) as JsonRecord;
  const integrity = isRecord(payload.integrity) ? payload.integrity : {};
  const expectedHash = integrity.packet_sha256 ?? null;
  delete payload.integrity;
  const actualHash = sha256(JSON.stringify(sortJson(payload)));
  const failures: JsonRecord[] = [];
  if (expectedHash !== actualHash) failures.push({ reason: "packet_sha256_mismatch", expected: expectedHash, actual: actualHash });
  const redaction = isRecord(packet.redaction) ? packet.redaction : {};
  if (redaction.raw_payload_included === true) failures.push({ reason: "raw_payload_included" });
  if (redaction.secret_value_present === true) failures.push({ reason: "secret_value_present" });
  failures.push(...findSuspiciousReleasePacketFields(packet));
  return {
    schema_version: "ashr.clone.release_evidence_packet_verification.v1",
    verified: failures.length === 0,
    packet_sha256: expectedHash,
    actual_packet_sha256: actualHash,
    failures,
  };
}

function releasePacketBindings(service: SaaSControlPlaneService, tenantId: string, projectId: string, runId: string, authKeyId: string): JsonRecord {
  const lifecycle = service.lifecycleSnapshot(tenantId, projectId, runId);
  const artifacts = service.listArtifactManifests(tenantId, projectId, runId, { authKeyId });
  const usage = service.usageSnapshot(tenantId, projectId, { authKeyId });
  const audit = service.auditSnapshot(tenantId, projectId, { runId, limit: 200, authKeyId });
  const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
  const traces = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
  const events = Array.isArray(usage.events) ? usage.events : [];
  const operationTotals = isRecord(usage.totals) ? usage.totals : {};
  const auditChain = isRecord(audit.chain) ? audit.chain : {};
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    counts: { uploads: uploads.length, trace_batches: traces.length, artifacts: artifacts.length },
    hashes: {
      uploads_sha256: sha256(JSON.stringify(sortJson(uploads))),
      trace_batches_sha256: sha256(JSON.stringify(sortJson(traces))),
      artifact_manifests_sha256: sha256(JSON.stringify(sortJson(artifacts))),
      usage_ledger_sha256: sha256(JSON.stringify(sortJson(events))),
    },
    usage: { operation_totals: cloneJson(operationTotals), billable_units: Object.values(operationTotals).reduce<number>((total, item) => total + Number(item ?? 0), 0) },
    audit_chain: { verified: auditChain.verified ?? null, event_count: auditChain.event_count ?? 0, tail_audit_event_sha256: auditChain.tail_audit_event_sha256 ?? null },
    bundle_root_sha256: sha256(JSON.stringify(sortJson({ artifacts, usage: operationTotals, audit_chain: auditChain }))),
  };
}

function verifyReleasePacketBindings(packet: JsonRecord, expected: JsonRecord): JsonRecord[] {
  const failures: JsonRecord[] = [];
  const packetCounts = isRecord(packet.counts) ? packet.counts : {};
  const expectedCounts = isRecord(expected.counts) ? expected.counts : {};
  for (const key of ["uploads", "trace_batches", "artifacts"]) {
    if (packetCounts[key] !== undefined && packetCounts[key] !== expectedCounts[key]) failures.push({ reason: `${key}_count_mismatch`, expected: expectedCounts[key], actual: packetCounts[key] });
  }
  const packetUsage = isRecord(packet.usage) ? packet.usage : {};
  const expectedUsage = isRecord(expected.usage) ? expected.usage : {};
  if (packetUsage.operation_totals !== undefined && JSON.stringify(sortJson(packetUsage.operation_totals)) !== JSON.stringify(sortJson(expectedUsage.operation_totals))) failures.push({ reason: "usage_operation_totals_mismatch", expected: expectedUsage.operation_totals, actual: packetUsage.operation_totals });
  if (packetUsage.billable_units !== undefined && packetUsage.billable_units !== expectedUsage.billable_units) failures.push({ reason: "usage_billable_units_mismatch", expected: expectedUsage.billable_units, actual: packetUsage.billable_units });
  const packetAudit = isRecord(packet.audit_chain) ? packet.audit_chain : {};
  const expectedAudit = isRecord(expected.audit_chain) ? expected.audit_chain : {};
  if (packetAudit.tail_audit_event_sha256 !== undefined && packetAudit.tail_audit_event_sha256 !== null && packetAudit.tail_audit_event_sha256 !== expectedAudit.tail_audit_event_sha256) failures.push({ reason: "audit_chain_tail_mismatch", expected: expectedAudit.tail_audit_event_sha256, actual: packetAudit.tail_audit_event_sha256 });
  const packetHashes = isRecord(packet.hashes) ? packet.hashes : {};
  const expectedHashes = isRecord(expected.hashes) ? expected.hashes : {};
  const artifactHash = packetHashes.artifacts_sha256 ?? packetHashes.artifact_manifests_sha256;
  if (artifactHash !== undefined && artifactHash !== expectedHashes.artifact_manifests_sha256) failures.push({ reason: "artifact_manifest_hash_mismatch", expected: expectedHashes.artifact_manifests_sha256, actual: artifactHash });
  const packetBindings = isRecord(packet.bindings) ? packet.bindings : {};
  if (packetBindings.bundle_root_sha256 !== undefined && packetBindings.bundle_root_sha256 !== expected.bundle_root_sha256) failures.push({ reason: "bundle_root_sha256_mismatch", expected: expected.bundle_root_sha256, actual: packetBindings.bundle_root_sha256 });
  return failures;
}

const SUSPICIOUS_RELEASE_PACKET_KEYS = new Set([
  "api_key",
  "authorization",
  "bearer",
  "cookie",
  "set_cookie",
  "password",
  "token",
  "access_token",
  "refresh_token",
  "client_secret",
  "secret",
  "raw_payload",
  "payload",
]);

function findSuspiciousReleasePacketFields(value: unknown, path = "$" ): JsonRecord[] {
  const failures: JsonRecord[] = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => failures.push(...findSuspiciousReleasePacketFields(item, `${path}[${index}]`)));
    return failures;
  }
  if (isRecord(value)) {
    Object.entries(value).forEach(([key, item]) => {
      const normalizedKey = key.toLowerCase().replace(/-/g, "_");
      const itemPath = `${path}.${key}`;
      if (SUSPICIOUS_RELEASE_PACKET_KEYS.has(normalizedKey)) failures.push({ reason: "suspicious_field_present", path: itemPath });
      failures.push(...findSuspiciousReleasePacketFields(item, itemPath));
    });
    return failures;
  }
  if (typeof value === "string") {
    const lowered = value.toLowerCase();
    if (lowered.startsWith("bearer ") || lowered.includes("ashr_api_key=")) failures.push({ reason: "suspicious_value_present", path });
  }
  return failures;
}

function secretHash(secret: string): string {
  return sha256(String(secret));
}

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function requestFingerprintSha256(request: JsonRecord): string {
  return sha256(JSON.stringify(sortJson(request)));
}

function newId(prefix: string): string {
  return `${prefix}_${Math.random().toString(16).slice(2, 14).padEnd(12, "0")}`;
}

function utcNow(): string {
  return new Date().toISOString();
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function jsonRecord(value: JsonRecord): JsonRecord {
  return cloneJson(sortJson(value)) as JsonRecord;
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => sortJson(item));
  if (isRecord(value)) {
    const result: JsonRecord = {};
    for (const key of Object.keys(value).sort()) result[key] = sortJson(value[key]);
    return result;
  }
  if (value === undefined) return null;
  return value;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stateBucket(payload: JsonRecord, key: string): Record<string, JsonRecord> {
  const value = payload[key] ?? {};
  if (!isRecord(value)) throw new ValidationError(`control-plane state ${key} must be an object`);
  const result: Record<string, JsonRecord> = {};
  for (const [itemKey, itemValue] of Object.entries(value)) {
    if (!isRecord(itemValue)) throw new ValidationError(`control-plane state ${key} records must be objects`);
    result[itemKey] = cloneJson(itemValue);
  }
  return result;
}

function optionalString(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  const parsed = String(value);
  return parsed.length > 0 ? parsed : undefined;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}
