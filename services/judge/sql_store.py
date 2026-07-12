"""SQLite-backed A2 evaluation store contract.

This module is intentionally small and dependency-free. It gives A2 a concrete
SQL read/write contract for evaluation results, calibration rows, golden cases,
and regression replay history without taking ownership of A1's production
Postgres runtime.
"""

from __future__ import annotations

from collections.abc import Iterable
import sqlite3
from typing import Any

from .result_persistence import canonical_json, stable_hash


SCHEMA_VERSION = "a2.sql_store_report.v1"
DDL_VERSION = "a2.sql_store.sqlite.v1"
DEFAULT_REPORT_ID = "a2_sql_store_report"
DEFAULT_CREATED_AT = "2026-07-09T00:00:00Z"
DDL_REF = "docs/a2/sql/a2_eval_store.sqlite.sql"

SQL_SCHEMA_TEXT = """-- A2 evaluation SQL store contract, SQLite reference dialect.
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
  ashr_available INTEGER NOT NULL CHECK (ashr_available IN (0, 1)),
  llm_available INTEGER NOT NULL CHECK (llm_available IN (0, 1)),
  local_failure_class TEXT NOT NULL,
  ashr_failure_class TEXT NOT NULL,
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
"""


def initialize_sql_store(connection: sqlite3.Connection) -> None:
    """Create all A2 SQL store tables and indexes."""
    connection.executescript(SQL_SCHEMA_TEXT)


def write_grade_report(
    connection: sqlite3.Connection,
    grade_report: dict[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> int:
    report_id = str(grade_report.get("report_id") or "a2_g3_grade_results")
    connection.execute(
        """
        INSERT OR REPLACE INTO a2_eval_runs (
          report_id, dataset_id, scenario_pack, total_cases, passed_cases,
          failed_cases, created_at, report_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_id,
            str(grade_report.get("dataset_id") or ""),
            str(grade_report.get("scenario_pack") or ""),
            _int(grade_report.get("total_cases")),
            _int(grade_report.get("passed")),
            _int(grade_report.get("failed")),
            created_at,
            stable_hash(grade_report),
        ),
    )
    rows = 0
    for case_result in _objects(grade_report.get("grade_results")):
        case_id = str(case_result.get("case_id") or case_result.get("scenario_id") or "")
        scenario_id = str(case_result.get("scenario_id") or "")
        for judge_result in _objects(case_result.get("judge_results")):
            judge_mode = str(judge_result.get("judge_mode") or "unknown_judge")
            failure_analysis = judge_result.get("failure_analysis") if isinstance(judge_result.get("failure_analysis"), dict) else {}
            result_id = stable_hash(
                {
                    "report_id": report_id,
                    "case_id": case_id,
                    "scenario_id": scenario_id,
                    "judge_mode": judge_mode,
                }
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO a2_judge_results (
                  result_id, report_id, case_id, scenario_id, judge_mode,
                  judge_version, passed, score, primary_failure_class,
                  safety_blocking, output_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    report_id,
                    case_id,
                    scenario_id,
                    judge_mode,
                    str(judge_result.get("judge_version") or ""),
                    _bool_int(judge_result.get("passed")),
                    _float(judge_result.get("score")),
                    str(failure_analysis.get("primary_failure_class") or case_result.get("primary_failure_class") or "none"),
                    _bool_int(failure_analysis.get("safety_blocking")),
                    stable_hash(judge_result),
                ),
            )
            rows += 1
    _log_ingest(connection, "grade_report", str(grade_report.get("schema_version") or ""), rows, grade_report, created_at)
    return rows


def write_calibration_matrix(
    connection: sqlite3.Connection,
    calibration_matrix: dict[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> int:
    dataset_id = str(calibration_matrix.get("dataset_id") or "")
    rows = 0
    for case in _objects(calibration_matrix.get("cases")):
        sources = case.get("sources") if isinstance(case.get("sources"), dict) else {}
        local = _dict(sources.get("local_judge"))
        ashr = _dict(sources.get("ashr_grading"))
        llm = _dict(sources.get("llm_judge"))
        disagreements = [
            diff
            for diff in _objects(case.get("diffs"))
            if str(diff.get("status")) == "mismatch"
        ]
        connection.execute(
            """
            INSERT OR REPLACE INTO a2_calibration_cases (
              case_id, dataset_id, scenario_id, fixture_ref, local_available,
              ashr_available, llm_available, local_failure_class,
              ashr_failure_class, llm_failure_class, disagreement_count,
              calibration_tags_json, row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(case.get("case_id") or ""),
                dataset_id,
                str(case.get("scenario_id") or ""),
                str(case.get("fixture_ref") or ""),
                _bool_int(local.get("available")),
                _bool_int(ashr.get("available")),
                _bool_int(llm.get("available")),
                str(local.get("primary_failure_class") or ""),
                str(ashr.get("primary_failure_class") or ""),
                str(llm.get("primary_failure_class") or ""),
                len(disagreements),
                canonical_json(_string_list(case.get("calibration_tags"))),
                stable_hash(case),
            ),
        )
        rows += 1
    _log_ingest(connection, "calibration_matrix", str(calibration_matrix.get("schema_version") or ""), rows, calibration_matrix, created_at)
    return rows


def write_golden_cases(
    connection: sqlite3.Connection,
    golden_payload: dict[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> int:
    golden_set_id = str(golden_payload.get("set_id") or "a2_golden_cases")
    rows = 0
    for case in _objects(golden_payload.get("goldenCases")):
        score_range = case.get("expected_score_range") if isinstance(case.get("expected_score_range"), list) else [0, 100]
        connection.execute(
            """
            INSERT OR REPLACE INTO a2_golden_cases (
              case_id, golden_set_id, scenario_id, expected_passed,
              expected_primary_failure_class, min_score, max_score,
              notes_hash, row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(case.get("case_id") or ""),
                golden_set_id,
                str(case.get("scenario_id") or ""),
                _bool_int(case.get("expected_passed")),
                str(case.get("expected_primary_failure_class") or "none"),
                _float(score_range[0] if score_range else 0),
                _float(score_range[1] if len(score_range) > 1 else 100),
                stable_hash(str(case.get("notes") or "")),
                stable_hash(case),
            ),
        )
        rows += 1
    _log_ingest(connection, "golden_cases", str(golden_payload.get("schema_version") or ""), rows, golden_payload, created_at)
    return rows


def write_regression_history(
    connection: sqlite3.Connection,
    regression_replay_report: dict[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> int:
    rows = 0
    for case in _objects(regression_replay_report.get("cases")):
        replay_grade = _dict(case.get("replay_grade"))
        connection.execute(
            """
            INSERT OR REPLACE INTO a2_regression_history (
              regression_id, case_id, scenario_id, replay_status,
              expected_local_failure_class, observed_local_failure_class,
              expected_llm_failure_class, replay_passed, replay_score,
              evidence_ref_count, row_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(case.get("regression_id") or ""),
                str(case.get("case_id") or ""),
                str(case.get("scenario_id") or ""),
                str(case.get("replay_status") or ""),
                str(case.get("expected_local_failure_class") or ""),
                str(case.get("observed_local_failure_class") or ""),
                str(case.get("expected_llm_failure_class") or ""),
                _bool_int(replay_grade.get("passed")),
                _float(replay_grade.get("score")),
                len(_string_list(case.get("evidence_refs"))),
                stable_hash(case),
            ),
        )
        rows += 1
    _log_ingest(
        connection,
        "regression_history",
        str(regression_replay_report.get("schema_version") or ""),
        rows,
        regression_replay_report,
        created_at,
    )
    return rows


def build_sql_store_report(
    grade_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    golden_payload: dict[str, Any],
    regression_replay_report: dict[str, Any],
    *,
    created_at: str = DEFAULT_CREATED_AT,
    report_id: str = DEFAULT_REPORT_ID,
    ddl_ref: str = DDL_REF,
) -> dict[str, Any]:
    """Write A2 artifacts into SQLite and read back a public-safe summary."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        initialize_sql_store(connection)
        write_counts = {
            "a2_judge_results": write_grade_report(connection, grade_report, created_at=created_at),
            "a2_calibration_cases": write_calibration_matrix(connection, calibration_matrix, created_at=created_at),
            "a2_golden_cases": write_golden_cases(connection, golden_payload, created_at=created_at),
            "a2_regression_history": write_regression_history(connection, regression_replay_report, created_at=created_at),
        }
        connection.commit()
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": report_id,
            "created_at": created_at,
            "database": {
                "engine": "sqlite",
                "reference_dialect": "sqlite",
                "production_target": "postgres-compatible contract owned by A1",
                "ddl_version": DDL_VERSION,
                "ddl_ref": ddl_ref,
            },
            "table_counts": _table_counts(connection),
            "write_counts": write_counts,
            "query_checks": _query_checks(connection),
            "source_refs": {
                "grade_report": "fixtures/a2/results/a2_g3_grade_results.json",
                "calibration_matrix": "fixtures/a2/results/a2_g3_calibration_matrix.json",
                "golden_cases": "fixtures/golden/a2_g2_golden_cases.json",
                "regression_replay": "fixtures/a2/results/a2_regression_replay_report.json",
                "ddl": ddl_ref,
            },
            "metadata": {
                "public_safe": True,
                "uses_python_stdlib_sqlite": True,
                "does_not_require_external_database": True,
                "does_not_execute_live_calls": True,
                "raw_private_evidence_not_recorded": True,
                "secrets_not_recorded": True,
                "intended_consumers": ["A2 calibration jobs", "A1 Postgres migration owner", "A3 report center"],
            },
        }
    finally:
        connection.close()


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "a2_eval_runs",
        "a2_judge_results",
        "a2_calibration_cases",
        "a2_golden_cases",
        "a2_regression_history",
        "a2_sql_ingest_log",
    )
    return {table: _count(connection, table) for table in tables}


def _query_checks(connection: sqlite3.Connection) -> dict[str, Any]:
    failure_rows = connection.execute(
        """
        SELECT primary_failure_class, COUNT(*) AS count
        FROM a2_judge_results
        GROUP BY primary_failure_class
        ORDER BY primary_failure_class
        """
    ).fetchall()
    calibration_rows = connection.execute(
        """
        SELECT
          SUM(CASE WHEN ashr_available = 0 THEN 1 ELSE 0 END) AS ashr_missing,
          SUM(disagreement_count) AS disagreement_count
        FROM a2_calibration_cases
        """
    ).fetchone()
    golden_rows = connection.execute(
        """
        SELECT expected_primary_failure_class, COUNT(*) AS count
        FROM a2_golden_cases
        WHERE expected_passed = 0
        GROUP BY expected_primary_failure_class
        ORDER BY expected_primary_failure_class
        """
    ).fetchall()
    regression_rows = connection.execute(
        """
        SELECT replay_status, COUNT(*) AS count
        FROM a2_regression_history
        GROUP BY replay_status
        ORDER BY replay_status
        """
    ).fetchall()
    return {
        "failure_class_counts": {str(row["primary_failure_class"]): int(row["count"]) for row in failure_rows},
        "golden_failure_class_counts": {
            str(row["expected_primary_failure_class"]): int(row["count"]) for row in golden_rows
        },
        "calibration_missing_ashr_count": int(calibration_rows["ashr_missing"] or 0),
        "calibration_disagreement_count": int(calibration_rows["disagreement_count"] or 0),
        "regression_replay_status_counts": {str(row["replay_status"]): int(row["count"]) for row in regression_rows},
        "can_join_case_level_history": _can_join_case_level_history(connection),
    }


def _can_join_case_level_history(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM a2_regression_history h
        JOIN a2_calibration_cases c ON c.case_id = h.case_id
        JOIN a2_judge_results j ON j.case_id = h.case_id
        """
    ).fetchone()
    return int(row["count"] or 0) > 0


def _log_ingest(
    connection: sqlite3.Connection,
    source_type: str,
    source_schema_version: str,
    row_count: int,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO a2_sql_ingest_log (
          ingest_id, source_type, source_schema_version, row_count,
          payload_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            stable_hash({"source_type": source_type, "source_schema_version": source_schema_version}),
            source_type,
            source_schema_version,
            row_count,
            stable_hash(payload),
            created_at,
        ),
    )


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def _objects(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _bool_int(value: Any) -> int:
    return 1 if value is True else 0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
