import hashlib
import hmac
import json
import sqlite3
import unittest

from services.judge.provider_gateway import ProviderDefinition, ProviderGateway, StrictFakeAdapter
from services.judge.provider_runtime import AUTHENTICATED_BUNDLE_SCHEMA_VERSION, validate_semantic_judge_output
from services.judge.release_decision_orchestrator import execute_release_decision
from services.judge.release_decision_store import IdempotencyConflictError, persist_release_decision
from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store


NOW = 1_750_000_000_000
KEY = b"k" * 32


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def run_result():
    return {
        "run_id": "run-1",
        "trace_completeness": 1,
        "aggregate_metrics": {"schema_version": "ashr.clone.run_result.v1"},
        "cases": [
            {
                "case_id": "case-1",
                "agent_output": {"final_response": "done"},
                "observations": [{"run_id": "run-1", "case_id": "case-1", "tool_calls": []}],
            }
        ],
    }


def signed_bundle(evidence=None):
    evidence = evidence or [run_result()]
    fields = {
        "schema_version": AUTHENTICATED_BUNDLE_SCHEMA_VERSION,
        "algorithm": "hmac-sha256",
        "key_id": "key-1",
        "bundle_id_digest": digest(b"bundle-1"),
        "tenant_digest": digest(b"tenant-a"),
        "project_digest": digest(b"project-a"),
        "evidence": evidence,
        "evidence_digest": digest(canonical(evidence)),
        "issued_at_unix_ms": NOW - 1000,
        "expires_at_unix_ms": NOW + 1000,
    }
    signing = {key: fields[key] for key in fields if key != "evidence"}
    fields["signature"] = hmac.new(KEY, canonical(signing), hashlib.sha256).hexdigest()
    return fields


def request(bundle=None):
    return {
        "organization_id": "org-a",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "project_id": "project-a",
        "environment_id": "test",
        "run_id": "run-1",
        "case_id": "case-1",
        "scenario_id": "A2-S001",
        "created_at": "2026-07-12T00:00:00Z",
        "required_modalities": ["text"],
        "provider_id": "unit",
        "model_id": "semantic-1",
        "idempotency_key": "decision-1",
        "authenticated_evidence_bundle": bundle or signed_bundle(),
    }


def gateway(response=None, *, failure="", audit_writer=None):
    provider = ProviderDefinition(
        "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}), data_residency="local"
    )
    response = response or {
        "output_text": json.dumps(
            {
                "passed": True,
                "score": 0.98,
                "reason": "evidence supports release",
                "failure_classes": [],
                "evidence_refs": ["snapshot"],
                "abstained": False,
            }
        ),
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }
    return ProviderGateway(
        [provider],
        {"fake": StrictFakeAdapter(response, failure=failure)},
        audit_writer=audit_writer,
        response_validator=validate_semantic_judge_output,
    )


class ReleaseDecisionOrchestratorTests(unittest.TestCase):
    def test_authenticated_normal_path_produces_allow_ledger_and_a3_handoff(self):
        original_request = request()
        original_json = json.dumps(original_request, sort_keys=True)
        provider_gateway = gateway()
        result = execute_release_decision(
            original_request, gateway=provider_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        repeated = execute_release_decision(
            original_request, gateway=provider_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        record = result["decision_ledger"]["records"][0]
        self.assertEqual(result, repeated)
        self.assertEqual(json.dumps(original_request, sort_keys=True), original_json)
        self.assertEqual(record["decision"], "allow")
        self.assertEqual(result["release_gate"]["decision"], "pass")
        self.assertFalse(result["a3_consumption"]["release_ready"])
        self.assertEqual(result["metadata"]["persistence_status"], "not_configured")
        self.assertFalse(result["a3_consumption"]["may_recompute_grade"])
        self.assertEqual(record["provider_summary"]["call_count"], 1)
        self.assertFalse(result["metadata"]["raw_evidence_included"])

    def test_provider_failure_or_invalid_json_cannot_become_pass(self):
        for candidate in (
            gateway(failure="timeout"),
            gateway({"output_text": "not-json", "usage": {}}),
        ):
            result = execute_release_decision(request(), gateway=candidate, key_resolver=lambda _: KEY, now_unix_ms=NOW)
            self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
            self.assertEqual(result["release_gate"]["decision"], "block")
            self.assertFalse(result["a3_consumption"]["release_ready"])

    def test_abstention_requires_review(self):
        response = {
            "output_text": json.dumps(
                {
                    "passed": False,
                    "score": 0.5,
                    "reason": "ambiguous evidence",
                    "failure_classes": [],
                    "evidence_refs": ["snapshot"],
                    "abstained": True,
                }
            ),
            "usage": {},
        }
        result = execute_release_decision(request(), gateway=gateway(response), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "review")
        self.assertTrue(result["a3_consumption"]["review_required"])

    def test_tampered_bundle_missing_modality_and_audit_failure_fail_closed(self):
        tampered = signed_bundle()
        tampered["evidence"][0]["run_id"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            execute_release_decision(request(tampered), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)

        missing = request()
        missing["required_modalities"] = ["text", "image"]
        result = execute_release_decision(missing, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
        self.assertIn("image", result["release_gate"]["blocking_reasons"])

        def broken_audit(_):
            raise OSError("ledger unavailable")

        result = execute_release_decision(
            request(), gateway=gateway(audit_writer=broken_audit), key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
        self.assertIn("audit_write_failed", result["release_gate"]["blocking_reasons"])

    def test_cross_tenant_bundle_is_rejected(self):
        cross = request()
        cross["tenant_id"] = "tenant-b"
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            execute_release_decision(cross, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)

    def test_atomic_commit_is_required_before_a3_can_release(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            result = execute_release_decision(
                request(),
                gateway=gateway(),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            repeated = execute_release_decision(
                request(),
                gateway=gateway(),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            self.assertTrue(result["a3_consumption"]["release_ready"])
            self.assertTrue(result["persistence"]["committed"])
            self.assertFalse(result["persistence"]["idempotent_replay"])
            self.assertTrue(repeated["persistence"]["idempotent_replay"])
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 1)
        finally:
            connection.close()

    def test_write_or_audit_failure_rolls_back_everything(self):
        for failure_step in ("after_decision", "after_audit"):
            connection = sqlite3.connect(":memory:")
            try:
                initialize_sql_store(connection)

                def fail(step):
                    if step == failure_step:
                        raise OSError("injected persistence failure")

                with self.assertRaisesRegex(OSError, "injected"):
                    execute_release_decision(
                        request(),
                        gateway=gateway(),
                        key_resolver=lambda _: KEY,
                        now_unix_ms=NOW,
                        persistence_connection=connection,
                        persistence_failure_injector=fail,
                    )
                self.assertEqual(_count(connection, "a2_release_decisions"), 0)
                self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            finally:
                connection.close()

    def test_changed_request_conflicts_with_existing_idempotency_key(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            changed = request()
            changed["policy_version"] = "a2.semantic_release_policy.v2"
            with self.assertRaisesRegex(IdempotencyConflictError, "different decision"):
                execute_release_decision(
                    changed, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection,
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
        finally:
            connection.close()

    def test_tampered_ledger_and_cross_scope_persist_nothing(self):
        base = execute_release_decision(request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        candidates = []
        tampered = json.loads(json.dumps(base))
        tampered["decision_ledger"]["records"][0]["record_hash"] = "sha256:tampered"
        candidates.append(tampered)
        cross_scope = json.loads(json.dumps(base))
        cross_scope["evidence_snapshot"]["tenant_id"] = "tenant-b"
        candidates.append(cross_scope)
        for candidate in candidates:
            connection = sqlite3.connect(":memory:")
            try:
                initialize_sql_store(connection)
                with self.assertRaises(ValueError):
                    persist_release_decision(
                        connection,
                        candidate,
                        idempotency_key="decision-1",
                        request_hash=stable_hash({"request": 1}),
                    )
                self.assertEqual(_count(connection, "a2_release_decisions"), 0)
                self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            finally:
                connection.close()

    def test_public_store_contains_hashes_not_raw_payloads_or_paths(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            dump = "\n".join(connection.iterdump())
            for forbidden in ("final_response", "output_text", "private_refs", "signed_url", "api_key", "Bearer "):
                self.assertNotIn(forbidden, dump)
        finally:
            connection.close()

    def test_provider_failure_is_committed_as_block_not_lost_or_allowed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            result = execute_release_decision(
                request(),
                gateway=gateway(failure="timeout"),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            stored = connection.execute(
                "SELECT decision FROM a2_release_decisions"
            ).fetchone()
            self.assertEqual(result["persistence"]["decision"], "block")
            self.assertEqual(stored[0], "block")
            self.assertFalse(result["a3_consumption"]["release_ready"])
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 1)
        finally:
            connection.close()


def _count(connection, table):
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
