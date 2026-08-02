import { createHash } from "node:crypto";

export const A3_BILLING_MIGRATION_READINESS_SCHEMA_VERSION = "a3.billing_migration_readiness.v1";
export const A3_BILLING_MIGRATION_READINESS_CONTRACT_ID = "a3_billing_migration_readiness_2026_07_09";
export const A3_BILLING_MIGRATION_READINESS_GENERATED_AT = "2026-07-09T00:00:00.000Z";

const UPSTREAM_COMMITS = [
  {
    sha: "f8ee956",
    full_sha: "f8ee9564ccdf0bf5e6be1fc00c70506dada51544",
    title: "A1: add billing ledger replay parity",
    evidence_kind: "replay_fixture_and_sdk_parity",
    files: [
      "docs/a1/evidence/billing_replay_fixture_round35.json",
      "docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json",
      "packages/ts/releasefoundry/src/billing.ts",
      "services/api/billing.py",
      "tests/a1/test_billing_provider_contract.py"
    ]
  },
  {
    sha: "91213fc",
    full_sha: "91213fc8b6fcf1fedb049c20a74407b8cd82ffd2",
    title: "A1: add durable billing ledger migration",
    evidence_kind: "durable_postgres_migration",
    files: [
      "docs/a1/schemas/a1_billing_ledger_migration_manifest.json",
      "services/api/migrations/002_a1_billing_ledger.sql",
      "tests/a1/test_billing_ledger_migration_manifest.py"
    ]
  },
  {
    sha: "11ac03e",
    full_sha: "11ac03ef999d2cc8080675f5d7bae638256a6498",
    title: "A1: add billing ledger live migration smoke",
    evidence_kind: "opt_in_live_migration_smoke",
    files: [
      "tests/integration/test_a1_billing_ledger_migration_live.py",
      "docs/a1/evidence/commands.md"
    ]
  }
];

const A1_BILLING_TABLES = [
  {
    name: "billing_accounts",
    purpose: "Provider customer/account reference per organization and project.",
    tenant_column: "organization_id",
    project_column: "project_id",
    rls_policy: "billing_accounts_organization_isolation",
    required_columns: [
      "id",
      "organization_id",
      "project_id",
      "provider",
      "mode",
      "customer_ref",
      "account_ref",
      "status",
      "metadata",
      "created_at",
      "updated_at",
      "deleted_at"
    ],
    required_indexes: ["idx_billing_accounts_scope"],
    required_constraints: [
      "billing_accounts_provider_customer_key",
      "billing_accounts_no_raw_secret"
    ]
  },
  {
    name: "billing_provider_events",
    purpose: "Provider webhook idempotency, signature summary, replay status, and hash-only payload reference.",
    tenant_column: "organization_id",
    project_column: "project_id",
    rls_policy: "billing_provider_events_organization_isolation",
    required_columns: [
      "id",
      "organization_id",
      "project_id",
      "billing_account_id",
      "provider",
      "mode",
      "provider_event_id",
      "provider_event_type",
      "payload_sha256",
      "signature_verified",
      "replay_status",
      "ledger_event_id",
      "raw_payload_included",
      "metadata",
      "created_at"
    ],
    required_indexes: [
      "idx_billing_provider_events_scope_created",
      "idx_billing_provider_events_replay"
    ],
    required_constraints: [
      "billing_provider_events_event_key",
      "billing_provider_events_no_raw_secret"
    ]
  },
  {
    name: "billing_ledger_events",
    purpose: "Append-only normalized billing ledger rows for invoices, refunds, cancellations, checkout, and usage reconciliation.",
    tenant_column: "organization_id",
    project_column: "project_id",
    rls_policy: "billing_ledger_events_organization_isolation",
    required_columns: [
      "id",
      "organization_id",
      "project_id",
      "billing_account_id",
      "provider_event_id",
      "event_type",
      "provider",
      "mode",
      "provider_event_ref",
      "customer_ref",
      "invoice_ref",
      "amount_minor",
      "currency",
      "usage_units",
      "metadata",
      "created_at"
    ],
    required_indexes: [
      "idx_billing_ledger_events_scope_created",
      "idx_billing_ledger_events_type_currency"
    ],
    required_constraints: [
      "billing_ledger_events_amount_check",
      "billing_ledger_events_no_raw_secret"
    ]
  }
];

const PROVIDER_EVENT_TYPES = [
  "checkout.session.completed",
  "checkout.session.async_payment_succeeded",
  "invoice.paid",
  "charge.refunded",
  "refund.created",
  "customer.subscription.deleted",
  "wechat_pay.transaction.success",
  "wechat_pay.refund.success",
  "alipay.trade.success",
  "alipay.trade.refund.success",
  "releasefoundry.usage.reconciled"
];

const LEDGER_EVENT_TYPES = [
  "checkout_created",
  "invoice_paid",
  "refund_created",
  "subscription_canceled",
  "usage_reconciled"
];

const SECRET_PATTERNS = [
  /\bsk_(?:test|live)_[A-Za-z0-9]{8,}\b/,
  /\brk_(?:test|live)_[A-Za-z0-9]{8,}\b/,
  /\bwhsec_[A-Za-z0-9]{8,}\b/,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
  /\bghp_[A-Za-z0-9]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
  /Cookie:\s*(?!\[REDACTED\])/i,
  /https:\/\/[^"\s]+X-Amz-Signature=/i,
  /(?:\d[ -]*?){13,19}/,
  /C:\\Users\\/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i
];

export function buildA3BillingMigrationReadiness(options = {}) {
  const body = {
    schema_version: A3_BILLING_MIGRATION_READINESS_SCHEMA_VERSION,
    contract_id: options.contractId || A3_BILLING_MIGRATION_READINESS_CONTRACT_ID,
    generated_at: options.generatedAt || A3_BILLING_MIGRATION_READINESS_GENERATED_AT,
    source_branch: "origin/agent/a1-local-sdk-runner",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local",
      environment_id: options.environmentId || "staging"
    },
    purpose: "Record A3's read-only consumption contract for A1 durable billing ledger migration, replay evidence, and live smoke proof.",
    summary: buildSummary(),
    upstream_commits: cloneJson(UPSTREAM_COMMITS).map((commit) => ({
      ...commit,
      a3_consumption_status: "consumed_from_public_git_diff",
      a3_write_scope_impact: "none_outside_a3_readiness_artifacts"
    })),
    upstream_evidence: buildUpstreamEvidence(),
    a3_consumer_state: buildA3ConsumerState(),
    api_contract: buildApiContract(),
    db_contract: {
      durable_backend_owner: "A1",
      a3_db_mutation_required: false,
      migration_manifest_schema: "releasefoundry.a1_billing_ledger_migration_manifest.v1",
      source_migration: "services/api/migrations/002_a1_billing_ledger.sql",
      tables: cloneJson(A1_BILLING_TABLES),
      functions: [
        {
          name: "normalize_billing_event_type",
          contract: "Maps provider event names to ledger event names."
        },
        {
          name: "ingest_billing_provider_event",
          contract: "Hash-only idempotent provider event ingestion with accepted, duplicate, and conflict replay statuses."
        },
        {
          name: "summarize_billing_ledger",
          contract: "Tenant/project-scoped currency totals, usage units, ledger event count, and provider event count."
        }
      ],
      required_safety: {
        rls_enabled_and_forced: true,
        organization_scope_required: true,
        project_scope_required: true,
        raw_payload_column_allowed: false,
        raw_provider_secret_allowed: false,
        raw_card_data_allowed: false,
        metadata_secret_checks_required: true
      }
    },
    event_contract: buildEventContract(),
    artifact_contract: buildArtifactContract(),
    tenant_auth_rbac_usage_audit: buildSecurityBoundary(),
    safety: {
      env_local_read: false,
      real_api_called_by_a3: false,
      live_database_migration_run_by_a3: false,
      real_payment_provider_called: false,
      billing_mutation_performed_by_a3: false,
      provider_secret_values_included: false,
      raw_provider_payload_included: false,
      raw_card_data_included: false,
      raw_customer_email_included: false,
      raw_signed_urls_included: false,
      fixture_output_path: "fixtures/a3/p3/a3_billing_migration_readiness.redacted.json"
    },
    acceptance: {
      node_test: "node --test tests/a3/a3_billing_migration_readiness.test.mjs",
      fixture: "fixtures/a3/p3/a3_billing_migration_readiness.redacted.json",
      documentation: "docs/a3/p3_billing_migration_readiness_2026_07_09.md",
      module: "services/report/a3_billing_migration_readiness.mjs"
    },
    next_actions: [
      "Ask A1 to expose a stable read-only billing ledger summary API before A3 shows live customer billing data.",
      "Keep A3 checkout, billing portal, and provider-webhook mutations disabled until A1 hosted auth, RBAC, webhook verification, RLS, and audit are live.",
      "Wire A3 billing UI only to redacted ledger summaries, event hashes, refs, counts, and invoice-preview totals.",
      "Add an A3 API route later only in an API-server scoped change; this contract intentionally stays in A3 report artifacts."
    ]
  };

  return {
    ...body,
    contract_hash: sha256(stableJson(body))
  };
}

export function validateA3BillingMigrationReadiness(contract = {}) {
  const errors = [];
  if (contract.schema_version !== A3_BILLING_MIGRATION_READINESS_SCHEMA_VERSION) {
    errors.push("schema_version must be a3.billing_migration_readiness.v1");
  }
  const commits = Array.isArray(contract.upstream_commits) ? contract.upstream_commits : [];
  for (const sha of ["f8ee956", "91213fc", "11ac03e"]) {
    if (!commits.some((commit) => commit.sha === sha)) {
      errors.push(`missing upstream commit ${sha}`);
    }
  }
  const dbTables = contract.db_contract?.tables || [];
  for (const table of ["billing_accounts", "billing_provider_events", "billing_ledger_events"]) {
    if (!dbTables.some((item) => item.name === table)) {
      errors.push(`missing DB table ${table}`);
    }
  }
  if (!contract.db_contract?.required_safety?.rls_enabled_and_forced) {
    errors.push("DB contract must require forced RLS");
  }
  if (contract.api_contract?.some((route) => route.a3_side_effect !== "none_read_only_contract")) {
    errors.push("all API contract entries must be read-only from A3");
  }
  if (!contract.event_contract?.provider_event_types?.includes("invoice.paid")) {
    errors.push("missing invoice.paid provider event type");
  }
  if (!contract.event_contract?.ledger_event_types?.includes("usage_reconciled")) {
    errors.push("missing usage_reconciled ledger event type");
  }
  if (!contract.artifact_contract?.a3_outputs?.some((artifact) => artifact.path === "fixtures/a3/p3/a3_billing_migration_readiness.redacted.json")) {
    errors.push("missing A3 redacted fixture output");
  }
  const boundary = contract.tenant_auth_rbac_usage_audit || {};
  if (boundary.usage?.billing_mutations_enabled !== false) {
    errors.push("usage boundary must keep billing mutations disabled");
  }
  if (boundary.auth?.raw_credentials_allowed !== false) {
    errors.push("auth boundary must reject raw credentials");
  }
  if (contract.safety?.env_local_read !== false) {
    errors.push("safety.env_local_read must be false");
  }
  if (contract.safety?.real_api_called_by_a3 !== false) {
    errors.push("safety.real_api_called_by_a3 must be false");
  }
  for (const leak of findA3BillingMigrationReadinessLeaks(contract)) {
    errors.push(`potential secret leak: ${leak.pattern}`);
  }
  if (!/^[a-f0-9]{64}$/.test(contract.contract_hash || "")) {
    errors.push("contract_hash must be a sha256 hex digest");
  }
  return { valid: errors.length === 0, errors };
}

export function findA3BillingMigrationReadinessLeaks(value) {
  const serialized = typeof value === "string" ? value : JSON.stringify(value);
  return SECRET_PATTERNS
    .filter((pattern) => pattern.test(serialized))
    .map((pattern) => ({ pattern: pattern.source }));
}

function buildSummary() {
  return {
    status: "read_only_migration_contract_ready",
    ready_for_live_customer_billing: false,
    consumed_evidence_count: 4,
    upstream_commit_count: UPSTREAM_COMMITS.length,
    consumed_states: {
      durable_migration_manifest: "mapped",
      replay_fixture: "mapped",
      live_smoke: "recognized_not_executed_by_a3",
      official_api_readonly_summary: "mapped"
    },
    a3_customer_claim: "A3 can display billing migration readiness and safety boundaries, but cannot claim live billing until A1 exposes authenticated read APIs and owns provider mutations."
  };
}

function buildUpstreamEvidence() {
  return {
    durable_billing_ledger_migration: {
      source_commit: "91213fc",
      manifest_path: "docs/a1/schemas/a1_billing_ledger_migration_manifest.json",
      migration_path: "services/api/migrations/002_a1_billing_ledger.sql",
      source_schema_version: "releasefoundry.a1_billing_ledger_migration_manifest.v1",
      version: 2,
      tables: cloneJson(A1_BILLING_TABLES),
      providers: ["stripe", "wechat_pay", "alipay"],
      modes: ["test", "live"],
      currencies: ["usd", "cny"],
      provider_event_types: cloneJson(PROVIDER_EVENT_TYPES),
      ledger_event_types: cloneJson(LEDGER_EVENT_TYPES),
      functions: ["normalize_billing_event_type", "ingest_billing_provider_event", "summarize_billing_ledger"],
      a3_consumption_state: "schema_and_safety_contract_consumed",
      public_safety: {
        raw_provider_payload_stored: false,
        raw_provider_secret_stored: false,
        raw_card_data_stored: false,
        provider_calls_executed: false
      }
    },
    replay_evidence: {
      source_commit: "f8ee956",
      fixture_path: "docs/a1/evidence/billing_replay_fixture_round35.json",
      source_schema_version: "releasefoundry.billing_replay_fixture.v1",
      provider_contract_schema_version: "releasefoundry.billing_provider_contract.v1",
      evidence_snapshot_schema_version: "releasefoundry.billing_evidence_snapshot.v1",
      replay_statuses_observed: ["accepted", "duplicate"],
      ledger_event_types_observed: ["invoice_paid", "usage_reconciled"],
      provider_event_count: 1,
      ledger_event_count: 2,
      totals_by_currency_minor: { usd: 12345 },
      usage_units: 14,
      raw_payload_included: false,
      secret_value_present: false,
      a3_consumption_state: "public_replay_fixture_consumed_as_redacted_read_model"
    },
    live_smoke: {
      source_commit: "11ac03e",
      test_path: "tests/integration/test_a1_billing_ledger_migration_live.py",
      execution_model: "opt_in_live_postgres",
      executed_by_a3: false,
      expected_idempotent_migration_replay: true,
      replay_statuses_expected: ["accepted", "duplicate", "conflict"],
      expected_rollup_terms: ["usd", "12345"],
      a3_consumption_state: "live_smoke_contract_read_from_diff_not_replayed"
    },
    official_api_readonly_summary: {
      source_commit: "f8ee956",
      summary_path: "docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json",
      source_schema_version: "releasefoundry.public_official_api_manifest_summary.v1",
      status: "ok",
      read_steps: 5,
      mutating_steps: 0,
      quota_block_count: 0,
      raw_records_private: true,
      public_summary_fields_only: true,
      a3_consumption_state: "official_readonly_status_consumed_without_api_call"
    }
  };
}

function buildA3ConsumerState() {
  return {
    state: "ready_to_consume_read_only_a1_billing_ledger_summary",
    a3_owned_surface: [
      "billing readiness report",
      "usage and invoice-preview UI",
      "commercial API contract mapping",
      "artifact and documentation evidence"
    ],
    a1_owned_surface: [
      "Postgres billing ledger migration",
      "provider webhook ingestion",
      "tenant auth and RLS enforcement",
      "billing provider executor",
      "billing ledger read APIs"
    ],
    a3_can_consume_now: [
      "migration manifest fields",
      "provider and ledger event type vocabulary",
      "public replay fixture counts and hashes",
      "live smoke expected replay statuses"
    ],
    blocked_for_live_customer_billing: [
      "no A1 authenticated read API is wired into A3 in this change",
      "no A1 billing provider webhook executor is callable by A3",
      "no hosted A1 auth/RBAC context is available to A3 billing UI",
      "no customer invoice or checkout mutation is allowed from A3"
    ],
    not_claimed_by_a3: [
      "A3 did not apply the A1 SQL migration",
      "A3 did not replay provider webhooks",
      "A3 did not read environment files",
      "A3 did not call the official ReleaseFoundry API",
      "A3 did not call Stripe, WeChat Pay, or Alipay"
    ]
  };
}

function buildApiContract() {
  return [
    {
      route: "GET /api/a3/billing/readiness",
      owner_lane: "A3",
      upstream_dependency: "A1 billing ledger summary when exposed",
      status: "existing_read_only_surface",
      rbac: "billing_admin_or_auditor",
      response_contract: "A3 billing readiness and invoice-preview metadata only",
      a3_side_effect: "none_read_only_contract"
    },
    {
      route: "future GET /v1/projects/{project_id}/billing/ledger-summary",
      owner_lane: "A1",
      upstream_dependency: "summarize_billing_ledger",
      status: "required_before_live_a3_customer_display",
      rbac: "billing_admin_or_auditor",
      response_contract: "currency totals, usage units, provider event count, ledger event count, no raw payload",
      a3_side_effect: "none_read_only_contract"
    },
    {
      route: "future GET /v1/projects/{project_id}/billing/provider-events",
      owner_lane: "A1",
      upstream_dependency: "billing_provider_events",
      status: "required_for_audit_readback",
      rbac: "billing_admin_or_auditor",
      response_contract: "event ids, event types, payload hashes, replay statuses, signature flags, no raw provider payload",
      a3_side_effect: "none_read_only_contract"
    },
    {
      route: "future POST /v1/billing/webhooks/{provider}",
      owner_lane: "A1",
      upstream_dependency: "ingest_billing_provider_event",
      status: "a1_only_mutation_not_callable_by_a3",
      rbac: "provider_webhook_verifier_service",
      response_contract: "accepted, duplicate, conflict, or rejected with ledger mutation count",
      a3_side_effect: "none_read_only_contract"
    }
  ];
}

function buildEventContract() {
  return {
    event_envelope_schema: "releasefoundry.event_envelope.v1",
    provider_event_types: cloneJson(PROVIDER_EVENT_TYPES),
    ledger_event_types: cloneJson(LEDGER_EVENT_TYPES),
    replay_statuses: ["accepted", "duplicate", "conflict", "rejected"],
    required_public_fields: [
      "organization_id",
      "project_id",
      "provider",
      "mode",
      "provider_event_id",
      "provider_event_type",
      "payload_sha256",
      "signature_verified",
      "replay_status",
      "ledger_event_id",
      "event_type",
      "currency",
      "amount_minor",
      "usage_units",
      "created_at"
    ],
    a3_consumer_events: [
      "billing.ledger_summary_read",
      "billing.provider_event_read",
      "billing.migration_readiness_viewed",
      "audit_event.created"
    ],
    payload_policy: "hashes, refs, statuses, counts, and normalized totals only"
  };
}

function buildArtifactContract() {
  return {
    upstream_inputs: [
      {
        path: "docs/a1/schemas/a1_billing_ledger_migration_manifest.json",
        owner_lane: "A1",
        a3_use: "DB table, function, provider, event, and public-safety contract source."
      },
      {
        path: "services/api/migrations/002_a1_billing_ledger.sql",
        owner_lane: "A1",
        a3_use: "RLS, idempotency, and no-raw-secret migration evidence."
      },
      {
        path: "docs/a1/evidence/billing_replay_fixture_round35.json",
        owner_lane: "A1",
        a3_use: "Public-safe accepted/duplicate replay and usage reconciliation evidence."
      },
      {
        path: "tests/integration/test_a1_billing_ledger_migration_live.py",
        owner_lane: "A1",
        a3_use: "Opt-in live smoke replay contract; not executed by A3."
      },
      {
        path: "docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json",
        owner_lane: "A1",
        a3_use: "Official API read-only safety status; A3 does not call the API."
      }
    ],
    a3_outputs: [
      {
        path: "services/report/a3_billing_migration_readiness.mjs",
        artifact_type: "contract_builder"
      },
      {
        path: "fixtures/a3/p3/a3_billing_migration_readiness.redacted.json",
        artifact_type: "redacted_fixture"
      },
      {
        path: "docs/a3/p3_billing_migration_readiness_2026_07_09.md",
        artifact_type: "readiness_doc"
      }
    ],
    retention_policy: "public-safe contract artifacts only; no private manifests, raw payloads, credentials, or customer emails"
  };
}

function buildSecurityBoundary() {
  return {
    tenant: {
      required_scope: ["organization_id", "project_id", "environment_id"],
      cross_tenant_default: "404_or_empty",
      durable_isolation_owner: "A1",
      a3_scope_behavior: "preserve tenant ids from A1 summary and never merge summaries across tenants"
    },
    auth: {
      current_a3_state: "read_only_contract",
      required_before_live_write: [
        "hosted session",
        "billing_admin actor id",
        "service account id for webhook/readback workers",
        "idempotency key",
        "A1 auth middleware"
      ],
      raw_credentials_allowed: false
    },
    rbac: {
      read_roles: ["billing_admin", "auditor", "owner"],
      mutation_roles: ["A1 provider_webhook_verifier_service"],
      a3_mutation_roles_enabled: [],
      denied_state_required: true,
      enforcement_state: "contract_only_until_A1_auth_RBAC"
    },
    usage: {
      source_of_truth: "A1 billing_ledger_events plus A1 usage rollups",
      a3_usage_display_mode: "read_only_preview",
      billable_meters: ["api_requests", "runs", "trace_events", "usage_units", "report_exports"],
      billing_mutations_enabled: false
    },
    audit: {
      append_only_required: true,
      actor_required: true,
      raw_payload_logged: false,
      payload_policy: "ids, refs, hashes, statuses, counts, and normalized totals only",
      required_event_types: [
        "billing.migration_readiness_viewed",
        "billing.ledger_summary_read",
        "billing.provider_event_read",
        "billing.mutation_blocked",
        "audit_event.created"
      ]
    }
  };
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

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}
