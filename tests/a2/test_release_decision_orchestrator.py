import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.judge.provider_gateway import ProviderDefinition, ProviderGateway, StrictFakeAdapter
from services.judge.provider_runtime import AUTHENTICATED_BUNDLE_SCHEMA_VERSION, validate_semantic_judge_output
from services.judge.release_decision_orchestrator import execute_release_decision
from services.judge.release_decision_store import (
    IdempotencyConflictError,
    authorize_provider_call,
    claim_decision_outbox,
    persist_provider_outcome,
    persist_release_decision,
    reserve_decision_operation,
    settle_decision_outbox,
)
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


class ProcessInterruptedAdapter:
    calls = 0

    def invoke(self, model, payload, timeout_seconds):
        self.calls += 1
        raise KeyboardInterrupt("worker terminated during provider call")


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
            self.assertEqual(_count(connection, "a2_decision_operations"), 1)
            self.assertEqual(_count(connection, "a2_decision_operation_audit"), 4)
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 1)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 1)
        finally:
            connection.close()

    def test_durable_retry_after_worker_restart_does_not_call_provider_again(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            first_gateway = gateway()
            first = execute_release_decision(
                request(), gateway=first_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            second_gateway = gateway()
            replay = execute_release_decision(
                request(), gateway=second_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            self.assertEqual(first_gateway.adapters["fake"].calls, 1)
            self.assertEqual(second_gateway.adapters["fake"].calls, 0)
            self.assertTrue(replay["persistence"]["idempotent_replay"])
            self.assertEqual(replay["persistence"]["record_hash"], first["persistence"]["record_hash"])
            self.assertTrue(replay["a3_consumption"]["release_ready"])
        finally:
            connection.close()

    def test_interrupted_provider_call_requires_recovery_and_is_not_replayed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            provider = ProviderDefinition(
                "unit", "interrupt", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                data_residency="local",
            )
            interrupted = ProcessInterruptedAdapter()
            interrupted_gateway = ProviderGateway(
                [provider],
                {"interrupt": interrupted},
                audit_writer=lambda _: None,
                response_validator=validate_semantic_judge_output,
            )
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=interrupted_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection,
                )
            retry_gateway = gateway()
            recovery = execute_release_decision(
                request(), gateway=retry_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            status = connection.execute(
                "SELECT status FROM a2_decision_operations"
            ).fetchone()[0]
            self.assertEqual(interrupted.calls, 1)
            self.assertEqual(retry_gateway.adapters["fake"].calls, 0)
            self.assertEqual(status, "recovery_required")
            self.assertEqual(recovery["metadata"]["persistence_status"], "recovery_required")
            self.assertTrue(recovery["a3_consumption"]["review_required"])
            self.assertFalse(recovery["a3_consumption"]["release_ready"])
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
        finally:
            connection.close()

    def test_active_reservation_replay_stays_in_progress_without_provider_call(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            scope = {
                "organization_id": "org-a",
                "tenant_id": "tenant-a",
                "workspace_id": "workspace-a",
                "project_id": "project-a",
                "environment_id": "test",
            }
            first = reserve_decision_operation(
                connection,
                scope=scope,
                idempotency_key="abandoned",
                request_hash="sha256:request",
                snapshot_id="sha256:snapshot-id",
                snapshot_hash="sha256:snapshot",
                provider_id="unit",
                model_id="semantic-1",
                created_at="2026-07-12T00:00:00Z",
            )
            replay = reserve_decision_operation(
                connection,
                scope=scope,
                idempotency_key="abandoned",
                request_hash="sha256:request",
                snapshot_id="sha256:snapshot-id",
                snapshot_hash="sha256:snapshot",
                provider_id="unit",
                model_id="semantic-1",
                created_at="2026-07-12T00:01:00Z",
            )
            self.assertEqual(first["status"], "reserved")
            self.assertEqual(replay["status"], "reserved")
            self.assertFalse(replay["provider_call_allowed"])
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "reserved",
            )
            self.assertEqual(_count(connection, "a2_decision_operation_audit"), 1)
        finally:
            connection.close()

    def test_reservation_failure_prevents_provider_invocation(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            provider_gateway = gateway()
            with patch(
                "services.judge.release_decision_orchestrator.reserve_decision_operation",
                side_effect=sqlite3.OperationalError("reservation unavailable"),
            ):
                with self.assertRaisesRegex(sqlite3.OperationalError, "reservation unavailable"):
                    execute_release_decision(
                        request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                        now_unix_ms=NOW, persistence_connection=connection,
                    )
            self.assertEqual(provider_gateway.adapters["fake"].calls, 0)
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_operations"), 0)
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

    def test_provider_outcome_failure_cannot_commit_decision(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(step):
                if step == "after_provider_outcome":
                    raise OSError("injected provider outcome failure")

            with self.assertRaisesRegex(OSError, "provider outcome"):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection, persistence_failure_injector=fail,
                )
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 0)
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "provider_running",
            )
        finally:
            connection.close()

    def test_outbox_failure_rolls_back_decision_operation_and_audit(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(step):
                if step == "after_outbox":
                    raise OSError("injected outbox failure")

            with self.assertRaisesRegex(OSError, "outbox"):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection, persistence_failure_injector=fail,
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "provider_completed",
            )
        finally:
            connection.close()

    def test_expired_lease_takeover_fences_old_worker(self):
        scope = {
            "organization_id": "org-a", "tenant_id": "tenant-a", "workspace_id": "workspace-a",
            "project_id": "project-a", "environment_id": "test",
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "a2-lease.sqlite"
            first_connection = sqlite3.connect(database)
            second_connection = sqlite3.connect(database)
            try:
                initialize_sql_store(first_connection)
                operation = reserve_decision_operation(
                    first_connection, scope=scope, idempotency_key="lease-case",
                    request_hash="sha256:request", snapshot_id="snapshot",
                    snapshot_hash="sha256:snapshot", provider_id="unit", model_id="semantic-1",
                    created_at="2026-07-12T00:00:00Z",
                )
                old_lease = authorize_provider_call(
                    first_connection, operation_id=operation["operation_id"], scope=scope,
                    created_at="2026-07-12T00:00:00Z", worker_id="worker-old", lease_seconds=1,
                )
                new_lease = authorize_provider_call(
                    second_connection, operation_id=operation["operation_id"], scope=scope,
                    created_at="2026-07-12T00:00:02Z", worker_id="worker-new", lease_seconds=60,
                )
                self.assertEqual(new_lease["fencing_token"], old_lease["fencing_token"] + 1)
                with self.assertRaisesRegex(ValueError, "stale fencing token"):
                    persist_provider_outcome(
                        first_connection, operation_id=operation["operation_id"], scope=scope,
                        lease=old_lease,
                        provider_result={"provider_id": "unit", "model_id": "semantic-1", "status": "ok"},
                        semantic_output={"passed": True}, completed_at="2026-07-12T00:00:03Z",
                    )
                persist_provider_outcome(
                    second_connection, operation_id=operation["operation_id"], scope=scope,
                    lease=new_lease,
                    provider_result={"provider_id": "unit", "model_id": "semantic-1", "status": "ok"},
                    semantic_output={"passed": True}, completed_at="2026-07-12T00:00:03Z",
                )
                self.assertEqual(_count(second_connection, "a2_provider_outcomes"), 1)
            finally:
                first_connection.close()
                second_connection.close()

    def test_outbox_delivery_is_fenced_retryable_and_idempotent(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            first = claim_decision_outbox(
                connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z", lease_seconds=1,
            )
            self.assertIsNotNone(first)
            self.assertEqual(first["attempt_count"], 1)
            takeover = claim_decision_outbox(
                connection, worker_id="dispatcher-b", now="2026-07-12T00:00:02Z",
            )
            self.assertEqual(takeover["lease_generation"], first["lease_generation"] + 1)
            with self.assertRaisesRegex(ValueError, "stale outbox"):
                settle_decision_outbox(
                    connection, event_id=first["event_id"], worker_id="dispatcher-a",
                    lease_generation=first["lease_generation"], delivered_at="2026-07-12T00:00:03Z",
                    outcome="delivered",
                )
            settle_decision_outbox(
                connection, event_id=takeover["event_id"], worker_id="dispatcher-b",
                lease_generation=takeover["lease_generation"], delivered_at="2026-07-12T00:00:03Z",
                outcome="retry", retry_at="2026-07-12T00:01:00Z", error_class="a3_unavailable",
            )
            self.assertIsNone(
                claim_decision_outbox(connection, worker_id="dispatcher-c", now="2026-07-12T00:00:30Z")
            )
            retry = claim_decision_outbox(
                connection, worker_id="dispatcher-c", now="2026-07-12T00:01:00Z",
            )
            settle_decision_outbox(
                connection, event_id=retry["event_id"], worker_id="dispatcher-c",
                lease_generation=retry["lease_generation"], delivered_at="2026-07-12T00:01:01Z",
                outcome="delivered",
            )
            self.assertIsNone(
                claim_decision_outbox(connection, worker_id="dispatcher-d", now="2026-07-12T00:02:00Z")
            )
            stored = connection.execute(
                "SELECT delivery_status, attempt_count, delivered_at FROM a2_decision_outbox"
            ).fetchone()
            self.assertEqual(stored, ("delivered", 3, "2026-07-12T00:01:01Z"))
        finally:
            connection.close()

    def test_outbox_rejects_invalid_settlement_and_never_reclaims_dead_event(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            with self.assertRaisesRegex(ValueError, "lease_seconds must be positive"):
                claim_decision_outbox(
                    connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
                    lease_seconds=0,
                )
            claimed = claim_decision_outbox(
                connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
            )
            with self.assertRaisesRegex(ValueError, "outbox outcome"):
                settle_decision_outbox(
                    connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                    lease_generation=claimed["lease_generation"],
                    delivered_at="2026-07-12T00:00:01Z", outcome="unknown",
                )
            with self.assertRaisesRegex(ValueError, "retry_at is required"):
                settle_decision_outbox(
                    connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                    lease_generation=claimed["lease_generation"],
                    delivered_at="2026-07-12T00:00:01Z", outcome="retry",
                )
            settle_decision_outbox(
                connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                lease_generation=claimed["lease_generation"],
                delivered_at="2026-07-12T00:00:01Z", outcome="dead",
                error_class="invalid_a3_contract",
            )
            self.assertIsNone(
                claim_decision_outbox(
                    connection, worker_id="dispatcher-b", now="2026-07-13T00:00:00Z",
                )
            )
            stored = connection.execute(
                "SELECT delivery_status, delivered_at, last_error_class "
                "FROM a2_decision_outbox"
            ).fetchone()
            self.assertEqual(stored, ("dead", None, "invalid_a3_contract"))
        finally:
            connection.close()

    def test_two_connections_cannot_claim_the_same_outbox_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "outbox.sqlite"
            first_connection = sqlite3.connect(database_path)
            second_connection = sqlite3.connect(database_path)
            try:
                initialize_sql_store(first_connection)
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=first_connection,
                )
                first = claim_decision_outbox(
                    first_connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
                )
                self.assertIsNotNone(first)
                self.assertIsNone(
                    claim_decision_outbox(
                        second_connection, worker_id="dispatcher-b", now="2026-07-12T00:00:01Z",
                    )
                )
                stored = second_connection.execute(
                    "SELECT lease_owner, lease_generation, attempt_count "
                    "FROM a2_decision_outbox WHERE event_id = ?",
                    (first["event_id"],),
                ).fetchone()
                self.assertEqual(
                    stored,
                    ("dispatcher-a", first["lease_generation"], 1),
                )
            finally:
                first_connection.close()
                second_connection.close()

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
            self.assertIn("a2.release_decision.committed.v1", dump)
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
