-- A2 evaluation SQL store contract, SQLite reference dialect.
-- Production Postgres migrations may adapt types, but must preserve table names,
-- key fields, hash semantics, and public-safe payload boundaries.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS a2_eval_runs (
  report_id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  scenario_pack TEXT NOT NULL,
  total_cases INTEGER NOT NULL CHECK (total_cases >= 0),
  passed_cases INTEGER NOT NULL CHECK (passed_cases >= 0),
  failed_cases INTEGER NOT NULL CHECK (failed_cases >= 0),
  created_at TEXT NOT NULL,
  report_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_judge_results (
  result_id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES a2_eval_runs(report_id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  judge_mode TEXT NOT NULL,
  judge_version TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  score REAL NOT NULL,
  primary_failure_class TEXT NOT NULL,
  safety_blocking INTEGER NOT NULL CHECK (safety_blocking IN (0, 1)),
  output_hash TEXT NOT NULL,
  UNIQUE(report_id, case_id, judge_mode)
);

CREATE TABLE IF NOT EXISTS a2_calibration_cases (
  case_id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  fixture_ref TEXT NOT NULL,
  local_available INTEGER NOT NULL CHECK (local_available IN (0, 1)),
  releasefoundry_available INTEGER NOT NULL CHECK (releasefoundry_available IN (0, 1)),
  llm_available INTEGER NOT NULL CHECK (llm_available IN (0, 1)),
  local_failure_class TEXT NOT NULL,
  releasefoundry_failure_class TEXT NOT NULL,
  llm_failure_class TEXT NOT NULL,
  disagreement_count INTEGER NOT NULL CHECK (disagreement_count >= 0),
  calibration_tags_json TEXT NOT NULL,
  row_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_golden_cases (
  case_id TEXT PRIMARY KEY,
  golden_set_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  expected_passed INTEGER NOT NULL CHECK (expected_passed IN (0, 1)),
  expected_primary_failure_class TEXT NOT NULL,
  min_score REAL NOT NULL,
  max_score REAL NOT NULL,
  notes_hash TEXT NOT NULL,
  row_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_regression_history (
  regression_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  replay_status TEXT NOT NULL,
  expected_local_failure_class TEXT NOT NULL,
  observed_local_failure_class TEXT NOT NULL,
  expected_llm_failure_class TEXT NOT NULL,
  replay_passed INTEGER NOT NULL CHECK (replay_passed IN (0, 1)),
  replay_score REAL NOT NULL,
  evidence_ref_count INTEGER NOT NULL CHECK (evidence_ref_count >= 0),
  row_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_sql_ingest_log (
  ingest_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_schema_version TEXT NOT NULL,
  row_count INTEGER NOT NULL CHECK (row_count >= 0),
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_release_decisions (
  record_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('allow', 'block', 'review')),
  review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
  snapshot_id TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL,
  provider_provenance_hash TEXT NOT NULL,
  judge_result_hash TEXT NOT NULL,
  release_gate_hash TEXT NOT NULL,
  previous_record_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL,
  ledger_id TEXT NOT NULL,
  ledger_hash TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(tenant_id, project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS a2_decision_operations (
  operation_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  reconciliation_mode TEXT NOT NULL DEFAULT 'unsupported' CHECK (
    reconciliation_mode IN ('unsupported', 'provider_status_lookup')
  ),
  provider_endpoint_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (
    status IN ('reserved', 'provider_running', 'provider_completed', 'committed', 'recovery_required')
  ),
  lease_owner TEXT,
  lease_expires_at TEXT,
  fencing_token INTEGER NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  recovery_owner TEXT,
  recovery_lease_expires_at TEXT,
  recovery_generation INTEGER NOT NULL DEFAULT 0 CHECK (recovery_generation >= 0),
  reconciliation_owner TEXT,
  reconciliation_lease_expires_at TEXT,
  reconciliation_generation INTEGER NOT NULL DEFAULT 0 CHECK (reconciliation_generation >= 0),
  reconciliation_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (reconciliation_attempt_count >= 0),
  reconciliation_next_at TEXT,
  last_reconciliation_status TEXT,
  last_reconciliation_observation_hash TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  provider_call_id TEXT,
  logical_call_id TEXT,
  provider_payload_hash TEXT,
  provider_idempotency_key_hash TEXT,
  provider_outcome_hash TEXT,
  record_id TEXT,
  record_hash TEXT,
  decision TEXT CHECK (decision IS NULL OR decision IN ('allow', 'block', 'review')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(
    organization_id, tenant_id, workspace_id, project_id, environment_id,
    idempotency_key
  )
);

CREATE TABLE IF NOT EXISTS a2_decision_operation_audit (
  audit_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES a2_decision_operations(operation_id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a2_provider_outcomes (
  provider_call_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES a2_decision_operations(operation_id) ON DELETE CASCADE,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  fencing_token INTEGER NOT NULL CHECK (fencing_token > 0),
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  normalized_status TEXT NOT NULL,
  response_hash TEXT NOT NULL,
  semantic_output_hash TEXT NOT NULL,
  usage_hash TEXT NOT NULL,
  outcome_hash TEXT NOT NULL,
  recovery_envelope_schema TEXT NOT NULL,
  recovery_envelope_json TEXT NOT NULL,
  recovery_envelope_hash TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(operation_id, fencing_token)
);

CREATE TABLE IF NOT EXISTS a2_provider_reconciliation_observations (
  observation_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES a2_decision_operations(operation_id) ON DELETE CASCADE,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  provider_call_id TEXT NOT NULL,
  provider_fencing_token INTEGER NOT NULL CHECK (provider_fencing_token > 0),
  reconciliation_generation INTEGER NOT NULL CHECK (reconciliation_generation > 0),
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  logical_call_id TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  idempotency_key_hash TEXT NOT NULL,
  query_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN (
      'remote_completed', 'remote_pending', 'remote_not_found',
      'remote_unknown', 'reconciliation_unsupported'
    )
  ),
  output_hash TEXT,
  normalized_output_json TEXT,
  normalized_output_hash TEXT,
  observation_hash TEXT NOT NULL,
  retry_authorized INTEGER NOT NULL DEFAULT 0 CHECK (retry_authorized = 0),
  observed_at TEXT NOT NULL,
  next_reconcile_at TEXT,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(operation_id, reconciliation_generation, observation_hash)
);

CREATE TABLE IF NOT EXISTS a2_release_decision_audit (
  audit_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(record_id, event_type)
);

CREATE TABLE IF NOT EXISTS a2_review_cases (
  review_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL, environment_id TEXT NOT NULL,
  machine_decision TEXT NOT NULL CHECK (machine_decision IN ('allow', 'block', 'review')),
  machine_record_hash TEXT NOT NULL, reason_code TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'leased', 'arbitration', 'completed')),
  required_approvals INTEGER NOT NULL DEFAULT 1 CHECK (required_approvals IN (1, 2)),
  lease_owner_hash TEXT, lease_generation INTEGER NOT NULL DEFAULT 0,
  lease_expires_at TEXT, final_event_id TEXT, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(record_id, reason_code)
);

CREATE TABLE IF NOT EXISTS a2_review_events (
  event_id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL REFERENCES a2_review_cases(review_id),
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL, environment_id TEXT NOT NULL, reviewer_id_hash TEXT NOT NULL,
  lease_generation INTEGER NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('confirm', 'overturn', 'abstain', 'escalate')),
  reason_code TEXT NOT NULL,
  superseding_record_id TEXT REFERENCES a2_release_decisions(record_id),
  event_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  release_authority INTEGER NOT NULL DEFAULT 0 CHECK (release_authority = 0),
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_a2_review_events_reviewer
  ON a2_review_events(review_id, reviewer_id_hash);

CREATE TABLE IF NOT EXISTS a2_review_resolutions (
  resolution_id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL UNIQUE REFERENCES a2_review_cases(review_id),
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL, environment_id TEXT NOT NULL,
  resolution_type TEXT NOT NULL CHECK (resolution_type IN ('review_consensus', 'arbitration')),
  final_outcome TEXT NOT NULL CHECK (final_outcome IN ('confirm', 'overturn')),
  superseding_record_id TEXT REFERENCES a2_release_decisions(record_id),
  effective_record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  effective_decision TEXT NOT NULL CHECK (effective_decision IN ('allow', 'block', 'review')),
  release_ready INTEGER NOT NULL CHECK (release_ready IN (0, 1)),
  machine_record_hash TEXT NOT NULL, superseding_record_hash TEXT,
  evidence_snapshot_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
  approval_count INTEGER NOT NULL CHECK (approval_count > 0),
  required_approvals INTEGER NOT NULL CHECK (required_approvals IN (1, 2)),
  arbitrator_id_hash TEXT, resolution_hash TEXT NOT NULL UNIQUE,
  resolved_at TEXT NOT NULL,
  release_authority INTEGER NOT NULL DEFAULT 1 CHECK (release_authority = 1),
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);

CREATE TABLE IF NOT EXISTS a2_review_resolution_outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL CHECK (event_type = 'a2.review_resolution.committed.v1'),
  resolution_id TEXT NOT NULL UNIQUE REFERENCES a2_review_resolutions(resolution_id),
  review_id TEXT NOT NULL UNIQUE REFERENCES a2_review_cases(review_id),
  organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL, environment_id TEXT NOT NULL,
  schema_version TEXT NOT NULL CHECK (schema_version = 'a2.human_review_resolution.v1'),
  payload_hash TEXT NOT NULL, resolution_hash TEXT NOT NULL,
  effective_record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  effective_decision TEXT NOT NULL CHECK (effective_decision IN ('allow', 'block', 'review')),
  release_ready INTEGER NOT NULL CHECK (release_ready IN (0, 1)),
  automatic_unblock INTEGER NOT NULL DEFAULT 0 CHECK (automatic_unblock = 0),
  delivery_status TEXT NOT NULL CHECK (
    delivery_status IN ('pending', 'leased', 'retry', 'delivered', 'dead')
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  lease_owner TEXT, lease_generation INTEGER NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  lease_expires_at TEXT, available_at TEXT NOT NULL, created_at TEXT NOT NULL,
  delivered_at TEXT, last_error_class TEXT,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);

CREATE TABLE IF NOT EXISTS a2_learning_candidates (
  candidate_id TEXT PRIMARY KEY,
  review_event_id TEXT NOT NULL REFERENCES a2_review_events(event_id),
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL, environment_id TEXT NOT NULL,
  consent_id_hash TEXT NOT NULL, purpose TEXT NOT NULL, lineage_hash TEXT NOT NULL,
  residency TEXT NOT NULL, retention_until TEXT NOT NULL, deletion_key_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('eligible', 'promoted', 'revoked', 'deleted')),
  cross_tenant_allowed INTEGER NOT NULL DEFAULT 0 CHECK (cross_tenant_allowed = 0),
  created_at TEXT NOT NULL, public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(review_event_id, purpose)
);

CREATE TABLE IF NOT EXISTS a2_decision_outbox (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  operation_id TEXT NOT NULL REFERENCES a2_decision_operations(operation_id),
  record_id TEXT NOT NULL REFERENCES a2_release_decisions(record_id),
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL,
  ledger_hash TEXT NOT NULL,
  provider_outcome_hash TEXT NOT NULL,
  delivery_status TEXT NOT NULL CHECK (
    delivery_status IN ('pending', 'leased', 'retry', 'delivered', 'dead')
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  lease_owner TEXT,
  lease_generation INTEGER NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  lease_expires_at TEXT,
  available_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  last_error_class TEXT,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1),
  UNIQUE(operation_id)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_consumptions (
  nonce_hash TEXT PRIMARY KEY,
  reference_id_hash TEXT NOT NULL,
  authorization_hash TEXT NOT NULL,
  issuer_hash TEXT NOT NULL,
  key_id_hash TEXT NOT NULL,
  issuer_key_target_hash TEXT NOT NULL,
  audience_hash TEXT NOT NULL,
  subject_hash TEXT NOT NULL,
  evaluation_job_id_hash TEXT NOT NULL,
  purpose TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('reserved', 'reading', 'resolved', 'failed_retryable', 'failed_terminal', 'revoked')
  ),
  reserved_at TEXT NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  fencing_token INTEGER NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  completed_at TEXT,
  failure_class TEXT,
  receipt_hash TEXT NOT NULL,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_events (
  event_id TEXT PRIMARY KEY,
  nonce_hash TEXT NOT NULL REFERENCES a2_artifact_reference_consumptions(nonce_hash),
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  lease_owner_hash TEXT NOT NULL,
  fencing_token INTEGER NOT NULL CHECK (fencing_token >= 0),
  occurred_at TEXT NOT NULL,
  details_hash TEXT NOT NULL,
  previous_event_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_revocations (
  revocation_id TEXT PRIMARY KEY,
  revocation_type TEXT NOT NULL CHECK (
    revocation_type IN ('reference', 'job', 'issuer_key', 'tenant_project')
  ),
  target_hash TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  revoked_at TEXT NOT NULL,
  UNIQUE(revocation_type, target_hash, tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_a2_judge_results_case ON a2_judge_results(case_id);
CREATE INDEX IF NOT EXISTS idx_a2_judge_results_failure ON a2_judge_results(primary_failure_class);
CREATE INDEX IF NOT EXISTS idx_a2_calibration_scenario ON a2_calibration_cases(scenario_id);
CREATE INDEX IF NOT EXISTS idx_a2_golden_scenario ON a2_golden_cases(scenario_id);
CREATE INDEX IF NOT EXISTS idx_a2_regression_scenario ON a2_regression_history(scenario_id);
CREATE INDEX IF NOT EXISTS idx_a2_release_decisions_scope
  ON a2_release_decisions(tenant_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_a2_decision_operations_status
  ON a2_decision_operations(tenant_id, project_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_a2_decision_operations_reconciliation_due
  ON a2_decision_operations(
    status, reconciliation_mode, reconciliation_next_at,
    reconciliation_lease_expires_at, created_at
  );
CREATE INDEX IF NOT EXISTS idx_a2_decision_outbox_delivery
  ON a2_decision_outbox(delivery_status, available_at);
CREATE INDEX IF NOT EXISTS idx_a2_review_resolution_outbox_delivery
  ON a2_review_resolution_outbox(delivery_status, available_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_consumptions_scope
  ON a2_artifact_reference_consumptions(tenant_id, project_id, status, reserved_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_consumptions_lease
  ON a2_artifact_reference_consumptions(status, lease_expires_at, reserved_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_events_nonce
  ON a2_artifact_reference_events(nonce_hash, occurred_at, event_id);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_revocations_target
  ON a2_artifact_reference_revocations(revocation_type, target_hash, tenant_id, project_id);
