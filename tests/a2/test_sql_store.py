import json
import re
import sqlite3
import unittest
from pathlib import Path

from services.judge.sql_store import (
    SQL_SCHEMA_TEXT,
    build_sql_store_report,
    initialize_sql_store,
    write_calibration_matrix,
    write_golden_cases,
    write_grade_report,
    write_regression_history,
)


ROOT = Path(__file__).resolve().parents[2]
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"
CALIBRATION_MATRIX = ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json"
GOLDEN_CASES = ROOT / "fixtures/golden/a2_g2_golden_cases.json"
REGRESSION_REPLAY = ROOT / "fixtures/a2/results/a2_regression_replay_report.json"
SQL_REPORT = ROOT / "fixtures/a2/results/a2_sql_store_report.json"
SQL_SCHEMA = ROOT / "docs/a2/schemas/sql_store_report.schema.json"
SQL_DDL = ROOT / "docs/a2/sql/a2_eval_store.sqlite.sql"

SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("releasefoundry_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2SqlStoreTests(unittest.TestCase):
    def test_sql_schema_file_matches_python_contract(self):
        self.assertEqual(SQL_DDL.read_text(encoding="utf-8").strip(), SQL_SCHEMA_TEXT.strip())
        ddl = SQL_DDL.read_text(encoding="utf-8")
        for table in (
            "a2_eval_runs",
            "a2_judge_results",
            "a2_calibration_cases",
            "a2_golden_cases",
            "a2_regression_history",
            "a2_sql_ingest_log",
            "a2_release_decisions",
            "a2_decision_operations",
            "a2_decision_operation_audit",
            "a2_provider_outcomes",
            "a2_release_decision_audit",
            "a2_decision_outbox",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", ddl)

    def test_operation_idempotency_is_isolated_by_full_scope(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            columns = (
                "operation_id", "idempotency_key", "organization_id", "tenant_id",
                "workspace_id", "project_id", "environment_id", "request_hash",
                "snapshot_id", "snapshot_hash", "provider_id", "model_id", "status",
                "created_at", "updated_at",
            )
            values = [
                "op-a", "shared-key", "org-a", "tenant-a", "workspace-a", "project-a",
                "test", "request-a", "snapshot-a", "snapshot-hash-a", "unit",
                "semantic-1", "reserved", "2026-07-12T00:00:00Z", "2026-07-12T00:00:00Z",
            ]
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO a2_decision_operations ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            values[0] = "op-b"
            values[4] = "workspace-b"
            values[7] = "request-b"
            values[8] = "snapshot-b"
            values[9] = "snapshot-hash-b"
            connection.execute(
                f"INSERT INTO a2_decision_operations ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM a2_decision_operations").fetchone()[0],
                2,
            )
        finally:
            connection.close()

    def test_sql_store_writes_and_reads_a2_core_artifacts(self):
        grade_report = load_json(GRADE_REPORT)
        calibration_matrix = load_json(CALIBRATION_MATRIX)
        golden_cases = load_json(GOLDEN_CASES)
        regression_replay = load_json(REGRESSION_REPLAY)

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            initialize_sql_store(connection)
            judge_rows = write_grade_report(connection, grade_report)
            calibration_rows = write_calibration_matrix(connection, calibration_matrix)
            golden_rows = write_golden_cases(connection, golden_cases)
            regression_rows = write_regression_history(connection, regression_replay)
            connection.commit()

            self.assertEqual(judge_rows, 160)
            self.assertEqual(calibration_rows, 6)
            self.assertEqual(golden_rows, 32)
            self.assertEqual(regression_rows, 1)
            self.assertEqual(_count(connection, "a2_eval_runs"), 1)
            self.assertEqual(_count(connection, "a2_judge_results"), 160)
            self.assertEqual(_count(connection, "a2_calibration_cases"), 6)
            self.assertEqual(_count(connection, "a2_golden_cases"), 32)
            self.assertEqual(_count(connection, "a2_regression_history"), 1)
            self.assertEqual(_count(connection, "a2_sql_ingest_log"), 4)

            join_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM a2_regression_history h
                JOIN a2_calibration_cases c ON c.case_id = h.case_id
                JOIN a2_judge_results j ON j.case_id = h.case_id
                """
            ).fetchone()["count"]
            self.assertGreater(join_count, 0)
        finally:
            connection.close()

    def test_sql_store_report_matches_fixture_and_schema(self):
        report = build_sql_store_report(
            load_json(GRADE_REPORT),
            load_json(CALIBRATION_MATRIX),
            load_json(GOLDEN_CASES),
            load_json(REGRESSION_REPLAY),
        )
        fixture = load_json(SQL_REPORT)
        schema = load_json(SQL_SCHEMA)

        self.assertEqual(report, fixture)
        self.assertEqual(schema["properties"]["schema_version"]["const"], report["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(report))
        self.assertEqual(report["database"]["ddl_ref"], "docs/a2/sql/a2_eval_store.sqlite.sql")
        self.assertEqual(report["table_counts"]["a2_judge_results"], 160)
        self.assertEqual(report["table_counts"]["a2_calibration_cases"], 6)
        self.assertEqual(report["table_counts"]["a2_golden_cases"], 32)
        self.assertEqual(report["table_counts"]["a2_regression_history"], 1)
        self.assertEqual(report["query_checks"]["calibration_missing_releasefoundry_count"], 6)
        self.assertEqual(report["query_checks"]["calibration_disagreement_count"], 1)
        self.assertTrue(report["query_checks"]["can_join_case_level_history"])
        self.assertTrue(report["metadata"]["public_safe"])
        self.assertTrue(report["metadata"]["uses_python_stdlib_sqlite"])
        self.assertTrue(report["metadata"]["does_not_require_external_database"])

        report_text = json.dumps(report, sort_keys=True)
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(report_text), pattern.pattern)


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


if __name__ == "__main__":
    unittest.main()
