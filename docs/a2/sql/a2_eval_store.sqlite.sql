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

CREATE INDEX IF NOT EXISTS idx_a2_judge_results_case ON a2_judge_results(case_id);
CREATE INDEX IF NOT EXISTS idx_a2_judge_results_failure ON a2_judge_results(primary_failure_class);
CREATE INDEX IF NOT EXISTS idx_a2_calibration_scenario ON a2_calibration_cases(scenario_id);
CREATE INDEX IF NOT EXISTS idx_a2_golden_scenario ON a2_golden_cases(scenario_id);
CREATE INDEX IF NOT EXISTS idx_a2_regression_scenario ON a2_regression_history(scenario_id);
