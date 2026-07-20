import json
import jsonschema
import re
import unittest
import tempfile
import threading
import base64
import os
import multiprocessing
import subprocess
import sys
from pathlib import Path

from services.judge.result_persistence import (
    build_result_persistence_manifest,
    build_result_record,
    build_ocr_vision_disagreement_record,
    build_multimodal_runtime_record,
    build_structured_output_failure_record,
    discover_directory_flush_capability,
    observe_filesystem_volume_hash,
    observe_parent_directory_durability,
    stable_hash,
    verify_jsonl_manifest,
    verify_jsonl_manifest_predecessor,
    write_jsonl,
)
from services.judge.ocr_contract import run_optional_ocr_adapter
from services.judge.local_multimodal_calibration import validate_prompt_lineage


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_FIXTURE = ROOT / "fixtures/a2/results/a2_result_persistence_manifest.json"
MANIFEST_SCHEMA = ROOT / "docs/a2/schemas/result_persistence_manifest.schema.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"
RELEASE_GATE = ROOT / "fixtures/a2/results/a2_release_gate_report.json"
RELEASE_UNBLOCK_CHECKLIST = ROOT / "fixtures/a2/results/a2_release_unblock_checklist.json"
SCENARIO_PACK = ROOT / "packages/scenarios/a2_g3_full_pack.json"
SCENARIO_SELECTION = ROOT / "fixtures/a2/results/a2_scenario_selection_report.json"
RUN_DIR = ROOT / "fixtures/a2/runs"

HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
REQUIRED_RECORD_FIELDS = {
    "tenant_id",
    "org",
    "project",
    "run",
    "case",
    "judge_version",
    "policy_hash",
    "input_hash",
    "output_hash",
    "created_at",
}
SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("ashr_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2ResultPersistenceTests(unittest.TestCase):
    def test_jsonl_manifest_round_trip_and_tamper_detection(self):
        records = [{"case": "one", "result": "BLOCK"}, {"case": "two", "result": "PASS"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.jsonl"
            manifest = write_jsonl(path, records)
            jsonschema.validate(
                manifest,
                load_json(ROOT / "docs/a2/schemas/result_persistence_jsonl_manifest.schema.json"),
            )
            verified = verify_jsonl_manifest(path, manifest)
            self.assertEqual(verified["state"], "verified")
            path.write_text(path.read_text(encoding="utf-8").replace("PASS", "BLOCK"), encoding="utf-8")
            tampered = verify_jsonl_manifest(path, manifest)
            self.assertEqual(tampered["state"], "blocked")
            self.assertIn("jsonl_file_hash_mismatch", tampered["blockers"])
            self.assertIn("jsonl_record_hash_mismatch", tampered["blockers"])
            self.assertIn("jsonl_chain_hash_mismatch", tampered["blockers"])

    def test_round30_predecessor_and_failed_replace_preserve_old_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.jsonl"
            second_path = Path(temp_dir) / "second.jsonl"
            first = write_jsonl(first_path, [{"case": "one"}])
            second = write_jsonl(
                second_path,
                [{"case": "two"}],
                sequence_number=2,
                previous_sequence_number=1,
                previous_manifest_hash=stable_hash(first),
                writer_build_hash="sha256:" + "1" * 64,
            )
            self.assertEqual(
                verify_jsonl_manifest_predecessor(
                    manifest=second, previous_manifest=first
                )["state"],
                "verified",
            )
            old = b'{"old": true}\n'
            target = Path(temp_dir) / "atomic.jsonl"
            target.write_bytes(old)
            with self.assertRaisesRegex(OSError, "injected"):
                write_jsonl(
                    target,
                    [{"new": True}],
                    replace_function=lambda *_: (_ for _ in ()).throw(OSError("injected")),
                )
            self.assertEqual(target.read_bytes(), old)
            self.assertFalse(target.with_name(target.name + ".tmp").exists())

    def test_round31_volume_reopen_predecessor_schema_and_replay_snapshot(self):
        from services.judge.provider_receipt_verification import (
            verify_provider_receipt_signature,
            verify_replay_set_snapshot,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reopen.jsonl"
            manifest = write_jsonl(
                path,
                [{"case": "round31"}],
                filesystem_volume_id_hash="sha256:" + "7" * 64,
            )
            self.assertEqual(manifest["post_replace_reopen_state"], "verified")
            self.assertEqual(
                manifest["durability_qualification_state"],
                "atomic_replace_verified_durability_unproven",
            )
            predecessor = verify_jsonl_manifest_predecessor(manifest=manifest, previous_manifest=None)
            jsonschema.validate(
                predecessor,
                load_json(ROOT / "docs/a2/schemas/result_persistence_predecessor_verification.schema.json"),
            )
        receipt = {"nonce": "public-safe"}
        signature = verify_provider_receipt_signature(
            receipt=receipt, issuer="test", signature_algorithm="test", verifier=lambda _: True
        )
        jsonschema.validate(
            signature,
            load_json(ROOT / "docs/a2/schemas/provider_receipt_signature_verification.schema.json"),
        )
        snapshot = {"receipt_hashes": ["sha256:" + "8" * 64], "nonce_hashes": ["sha256:" + "9" * 64]}
        good = verify_replay_set_snapshot(snapshot=snapshot, expected_snapshot_hash=stable_hash(snapshot))
        bad = verify_replay_set_snapshot(
            snapshot={**snapshot, "nonce_hashes": []}, expected_snapshot_hash=stable_hash(snapshot)
        )
        self.assertEqual(good["state"], "verified")
        self.assertIn("provider_receipt_replay_set_tampered", bad["blockers"])

    def test_round32_ed25519_operation_binding_replay_race_and_corruption(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from services.judge.provider_receipt_verification import (
            PersistentReplaySet,
            ReplaySet,
            verify_ed25519_receipt,
            verify_receipt_operation_binding,
        )
        receipt = {
            "request_hash": "sha256:" + "1" * 64,
            "cancellation_operation_id_hash": "sha256:" + "2" * 64,
            "nonce_hash": "sha256:" + "3" * 64,
        }
        private = Ed25519PrivateKey.generate()
        signed_identity = {
            "signature_algorithm": "ed25519",
            "canonicalization_version": "rfc8785-subset-json-v1",
            "receipt": receipt,
        }
        message = json.dumps(signed_identity, sort_keys=True, separators=(",", ":")).encode()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        verified = verify_ed25519_receipt(
            receipt=receipt,
            signature_base64=base64.b64encode(private.sign(message)).decode(),
            public_key_base64=base64.b64encode(public).decode(),
            issuer="local-test",
            key_id="key-1",
            key_policy={
                "schema_version": "a2.provider_receipt_key_policy.v1",
                "allowed_keys": {
                    "key-1": {
                        "issuer": "local-test",
                        "state": "active",
                        "effective_at_unix_ms": 100,
                        "expires_at_unix_ms": 300,
                    }
                },
            },
            now_unix_ms=200,
        )
        self.assertEqual(verified["verification_state"], "verified")
        binding = verify_receipt_operation_binding(
            receipt=receipt,
            expected_request_hash=receipt["request_hash"],
            expected_operation_id_hash=receipt["cancellation_operation_id_hash"],
        )
        self.assertEqual(binding["state"], "verified")
        replay = ReplaySet()
        outcomes = []
        threads = [threading.Thread(target=lambda: outcomes.append(replay.admit(receipt["nonce_hash"]))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count(True), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.jsonl"
            with self.assertRaisesRegex(OSError, "post-replace"):
                write_jsonl(
                    path,
                    [{"case": "x"}],
                    replay_set_snapshot=replay.snapshot(),
                    post_replace_hook=lambda target: target.write_bytes(b"corrupt"),
                )

        with tempfile.TemporaryDirectory() as directory:
            persistent_path = Path(directory) / "replay.json"
            self.assertTrue(PersistentReplaySet(persistent_path).admit(receipt["nonce_hash"])["admitted"])
            self.assertFalse(PersistentReplaySet(persistent_path).admit(receipt["nonce_hash"])["admitted"])

    def test_round33_receipt_key_time_rotation_and_identity_fail_closed(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from services.judge.provider_receipt_verification import verify_ed25519_receipt

        receipt = {"nonce_hash": "sha256:" + "4" * 64}
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        identity = {
            "signature_algorithm": "ed25519",
            "canonicalization_version": "rfc8785-subset-json-v1",
            "receipt": receipt,
        }
        signature = base64.b64encode(
            private.sign(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
        ).decode()

        def verify(state="active", now=200, algorithm="ed25519", canonicalization="rfc8785-subset-json-v1"):
            return verify_ed25519_receipt(
                receipt=receipt,
                signature_base64=signature,
                public_key_base64=base64.b64encode(public).decode(),
                issuer="issuer",
                key_id="rotating",
                key_policy={
                    "schema_version": "a2.provider_receipt_key_policy.v1",
                    "allowed_keys": {
                        "rotating": {
                            "issuer": "issuer",
                            "state": state,
                            "effective_at_unix_ms": 100,
                            "expires_at_unix_ms": 300,
                        }
                    },
                },
                now_unix_ms=now,
                signature_algorithm=algorithm,
                canonicalization_version=canonicalization,
            )

        self.assertEqual(verify()["verification_state"], "verified")
        self.assertIn("provider_receipt_key_not_yet_active", verify(now=99)["blockers"])
        self.assertIn("provider_receipt_key_expired", verify(now=300)["blockers"])
        self.assertIn("provider_receipt_key_not_active", verify(state="revoked")["blockers"])
        self.assertIn(
            "provider_receipt_signature_algorithm_unsupported",
            verify(algorithm="rsa")["blockers"],
        )
        self.assertIn(
            "provider_receipt_canonicalization_unsupported",
            verify(canonicalization="legacy-json")["blockers"],
        )

    def test_round33_persistent_replay_set_multiprocess_contention(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multiprocess-replay.json"
            program = (
                "from services.judge.provider_receipt_verification import PersistentReplaySet;"
                "import sys;"
                "print(int(PersistentReplaySet(sys.argv[1]).admit(sys.argv[2])['admitted']))"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", program, str(path), "sha256:" + "7" * 64],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(6)
            ]
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                results.append(int(stdout.strip()))
            self.assertEqual(results.count(1), 1)

    def test_round34_key_rotation_policy_and_shared_canonicalization(self):
        from services.judge.provider_receipt_verification import (
            canonicalize_signed_receipt,
            validate_provider_receipt_key_policy,
        )

        receipt = {"unicode": "安全", "nested": {"b": 2, "a": 1}}
        self.assertEqual(
            canonicalize_signed_receipt(receipt),
            (
                b'{"canonicalization_version":"rfc8785-subset-json-v1",'
                b'"receipt":{"nested":{"a":1,"b":2},"unicode":"\\u5b89\\u5168"},'
                b'"signature_algorithm":"ed25519"}'
            ),
        )
        valid = validate_provider_receipt_key_policy(
            {
                "schema_version": "a2.provider_receipt_key_policy.v1",
                "allow_rotation_overlap": True,
                "key_records": [
                    {
                        "issuer": "provider",
                        "key_id": "old",
                        "effective_at_unix_ms": 100,
                        "expires_at_unix_ms": 250,
                    },
                    {
                        "issuer": "provider",
                        "key_id": "new",
                        "effective_at_unix_ms": 200,
                        "expires_at_unix_ms": 400,
                    },
                ],
            }
        )
        self.assertEqual(valid["state"], "verified")
        ambiguous = validate_provider_receipt_key_policy(
            {
                "schema_version": "a2.provider_receipt_key_policy.v1",
                "key_records": [
                    {
                        "issuer": "provider",
                        "key_id": "duplicate",
                        "effective_at_unix_ms": 100,
                        "expires_at_unix_ms": 200,
                    },
                    {
                        "issuer": "provider",
                        "key_id": "duplicate",
                        "effective_at_unix_ms": 300,
                        "expires_at_unix_ms": 400,
                    },
                ],
            }
        )
        self.assertIn("provider_receipt_key_identity_ambiguous", ambiguous["blockers"])
        self.assertIn("provider_receipt_key_rotation_handoff_gap", ambiguous["blockers"])

    def test_round34_replay_chain_crash_and_lock_timeout_fail_closed(self):
        from services.judge.provider_receipt_verification import (
            PersistentReplaySet,
            _lock_file,
            _unlock_file,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            replay = PersistentReplaySet(path)
            first = replay.admit("sha256:" + "1" * 64)
            first_snapshot = json.loads(path.read_text(encoding="utf-8"))
            second = replay.admit("sha256:" + "2" * 64)
            second_snapshot = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(first["admitted"])
            self.assertTrue(second["admitted"])
            self.assertEqual(second_snapshot["sequence_number"], 2)
            self.assertEqual(second_snapshot["predecessor_hash"], stable_hash(first_snapshot))

            def crash_after_fsync(_temporary):
                raise RuntimeError("injected crash")

            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                PersistentReplaySet(path, after_fsync_hook=crash_after_fsync).admit(
                    "sha256:" + "3" * 64
                )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), second_snapshot)

            lock_path = path.with_suffix(path.suffix + ".lock")
            with lock_path.open("a+b") as held:
                self.assertTrue(_lock_file(held, timeout_seconds=1.0))
                try:
                    outcome = PersistentReplaySet(
                        path, lock_timeout_seconds=0.05
                    ).admit("sha256:" + "4" * 64)
                finally:
                    _unlock_file(held)
            self.assertFalse(outcome["admitted"])
            self.assertEqual(outcome["lock_state"], "timeout_blocked")
            self.assertEqual(
                outcome["lock_diagnostics"],
                {
                    "ownership_state": "held_by_other_process",
                    "owner_identity_exposed": False,
                    "wait_bucket": "under_1s",
                },
            )
            self.assertIn("provider_receipt_replay_lock_timeout", outcome["blockers"])

    def test_round35_durability_receipt_separates_and_hash_binds_each_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_jsonl(
                Path(directory) / "result.jsonl",
                [{"case": "durability"}],
                parent_directory_flush_evidence={
                    "flush_attempted": True,
                    "flush_succeeded": True,
                },
            )
        self.assertEqual(
            manifest["durability_receipt"],
            {
                "file_write_state": "completed",
                "file_fsync_state": "verified",
                "atomic_replace_state": "verified",
                "post_replace_reopen_state": "verified",
                "parent_directory_flush_state": "verified",
            },
        )
        self.assertEqual(
            manifest["durability_receipt_hash"],
            stable_hash(manifest["durability_receipt"]),
        )

    def test_round35_jsonl_crash_injection_preserves_expected_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.jsonl"
            original = b'{"case":"original"}\n'
            path.write_bytes(original)

            def crash(stage):
                if stage == "after_file_fsync":
                    raise RuntimeError(stage)

            with self.assertRaisesRegex(RuntimeError, "after_file_fsync"):
                write_jsonl(path, [{"case": "replacement"}], crash_injector=crash)
            self.assertEqual(path.read_bytes(), original)

            def crash_after_replace(stage):
                if stage == "after_atomic_replace":
                    raise RuntimeError(stage)

            with self.assertRaisesRegex(RuntimeError, "after_atomic_replace"):
                write_jsonl(
                    path,
                    [{"case": "replacement"}],
                    crash_injector=crash_after_replace,
                )
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"case": "replacement"}\n',
            )

    def test_round35_windows_volume_observer_false_return_is_public_safe(self):
        observed = observe_filesystem_volume_hash(
            "C:/governed/result.jsonl",
            platform_name="nt",
            windows_volume_observer=lambda _root: False,
        )
        self.assertEqual(observed["observation_state"], "fallback")
        self.assertEqual(observed["error_class"], "volume_api_os_error")
        self.assertFalse(observed["raw_identifier_exposed"])
        jsonschema.validate(
            observed,
            load_json(ROOT / "docs/a2/schemas/filesystem_volume_observation.schema.json"),
        )

        successful = observe_filesystem_volume_hash(
            "C:/governed/result.jsonl",
            platform_name="nt",
            windows_volume_observer=lambda _root: 12345,
        )
        self.assertEqual(successful["observation_state"], "observed")
        self.assertEqual(successful["error_class"], "none")
        jsonschema.validate(
            successful,
            load_json(ROOT / "docs/a2/schemas/filesystem_volume_observation.schema.json"),
        )

    def test_round35_replay_snapshot_rollback_and_fork_fail_closed(self):
        from services.judge.provider_receipt_verification import PersistentReplaySet

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            replay = PersistentReplaySet(path)
            replay.admit("sha256:" + "a" * 64)
            first_snapshot = json.loads(path.read_text(encoding="utf-8"))
            replay.admit("sha256:" + "b" * 64)

            path.write_text(json.dumps(first_snapshot), encoding="utf-8")
            rollback = PersistentReplaySet(path, minimum_sequence_number=2).admit(
                "sha256:" + "c" * 64
            )
            self.assertIn(
                "provider_receipt_replay_snapshot_rollback", rollback["blockers"]
            )

            fork = PersistentReplaySet(
                path,
                minimum_sequence_number=1,
                expected_snapshot_hash=stable_hash(
                    {**first_snapshot, "nonce_hashes": ["sha256:" + "f" * 64]}
                ),
            ).admit("sha256:" + "d" * 64)
            self.assertIn("provider_receipt_replay_snapshot_fork", fork["blockers"])

    def test_round34_windows_volume_errors_are_public_safe_classes(self):
        from services.judge.result_persistence import _classify_windows_volume_error

        self.assertEqual(
            _classify_windows_volume_error(PermissionError("private path")),
            "permission_denied",
        )
        self.assertEqual(
            _classify_windows_volume_error(FileNotFoundError("private root")),
            "volume_root_not_found",
        )
        self.assertEqual(
            _classify_windows_volume_error(OSError("raw operating system detail")),
            "volume_api_os_error",
        )
        with tempfile.TemporaryDirectory() as directory:
            observation = observe_filesystem_volume_hash(directory)
        self.assertIn(observation["observation_state"], {"observed", "fallback"})
        self.assertNotIn("raw operating system detail", json.dumps(observation))
        self.assertFalse(observation["raw_identifier_exposed"])

    def test_round32_volume_observation_and_directory_flush_discovery_are_public_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = observe_filesystem_volume_hash(directory)
        self.assertRegex(observation["filesystem_volume_id_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertFalse(observation["raw_identifier_exposed"])
        self.assertIn(
            observation["observation_method"],
            {"resolved_drive_hash", "windows_volume_api_hashed"},
        )
        capability = discover_directory_flush_capability()
        self.assertIn(capability["directory_flush_state"], {"supported", "not_exposed"})
        self.assertTrue(capability["public_safe"])
        if os.name == "nt":
            self.assertFalse(capability["durability_claim_allowed"])
        with tempfile.TemporaryDirectory() as directory:
            durability = observe_parent_directory_durability(Path(directory) / "result.jsonl")
        self.assertTrue(durability["public_safe"])
        if os.name == "nt":
            self.assertFalse(durability["durability_claim_allowed"])
            self.assertIn("parent_directory_flush_evidence_unavailable", durability["blockers"])

    def test_jsonl_manifest_chains_batches_and_blocks_truncated_line(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.jsonl"
            second_path = Path(directory) / "second.jsonl"
            first = write_jsonl(first_path, [{"case": "one"}])
            second = write_jsonl(
                second_path,
                [{"case": "two"}],
                previous_manifest_hash=stable_hash(first),
                previous_sequence_number=1,
                sequence_number=2,
            )
            self.assertEqual(second["previous_manifest_hash"], stable_hash(first))
            self.assertEqual(verify_jsonl_manifest(second_path, second)["state"], "verified")
            second_path.write_text('{"case":"two"}\n{"case":', encoding="utf-8")
            truncated = verify_jsonl_manifest(second_path, second)
            self.assertEqual(truncated["state"], "blocked")
            self.assertIn("jsonl_parse_failure", truncated["blockers"])

    def test_jsonl_sequence_pin_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "batch.jsonl"
            path.write_text('{"stale": true}\n', encoding="utf-8")
            manifest = write_jsonl(
                path, [{"case": "fresh"}], sequence_number=3, previous_sequence_number=2
            )
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            replay = verify_jsonl_manifest(
                path,
                manifest,
                expected_sequence_number=4,
                pinned_chain_hash="sha256:" + "0" * 64,
            )
            self.assertIn("jsonl_sequence_gap_or_replay", replay["blockers"])
            self.assertIn("jsonl_chain_head_pin_mismatch", replay["blockers"])
            verified = verify_jsonl_manifest(
                path,
                manifest,
                expected_sequence_number=3,
                pinned_chain_hash=manifest["chain_hash"],
            )
            self.assertEqual(verified["state"], "verified")

    def test_multimodal_runtime_timeout_receipts_persist_hash_only(self):
        receipt = "sha256:" + "9" * 64
        record = build_multimodal_runtime_record(
            {
                "schema_version": "a2.multimodal_runtime_policy.v1",
                "observation_count": 2,
                "maximum_latency_seconds": 30,
                "maximum_completion_tokens": 48,
                "maximum_provider_timeout_rate": 0.1,
                "minimum_valid_semantic_output_rate": 0.9,
                "timeout_count": 1,
                "provider_timeout_rate": 0.5,
                "completed_count": 1,
                "completed_semantic_count": 0,
                "empty_response_count": 1,
                "valid_semantic_output_rate": 0,
                "qualification_state": "blocked",
                "blockers": ["multimodal_runtime_provider_timeout"],
                "queue_telemetry": {"state": "not_exposed", "maximum_depth": None},
                "cancellation_receipt_hashes": [receipt],
                "public_safe": True,
                "raw_response": "must-not-persist",
            },
            org_id="org",
            project_id="project",
            run_id="run",
            case_id="case",
            judge_version="a2-runtime-v1",
            created_at="2026-07-13T00:00:00Z",
        )
        text = json.dumps(record)
        self.assertEqual(record["record_type"], "multimodal_runtime")
        self.assertNotIn("must-not-persist", text)
        self.assertNotIn(receipt, text)
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))

    def test_ocr_vision_disagreement_record_is_hash_only(self):
        disagreement = {"state": "disagreement", "artifact_hash": "sha256:" + "1" * 64, "ocr_observation_hash": "sha256:" + "2" * 64, "vision_output_hash": "sha256:" + "3" * 64, "reason_code": "vision_hallucinated_text", "review_packet_hash": "sha256:" + "4" * 64, "blockers": ["ocr_vision_text_disagreement"], "raw_text": "do not persist"}
        record = build_ocr_vision_disagreement_record(disagreement, org_id="org", project_id="project", run_id="run", case_id="case", created_at="2026-07-13T00:00:00Z")
        self.assertEqual(record["record_type"], "ocr_vision_disagreement")
        self.assertNotIn("do not persist", json.dumps(record))

    def test_structured_output_failure_record_is_hash_only(self):
        receipt = {
            "state": "invalid_json",
            "provider_status": "completed",
            "raw_response_hash": "sha256:" + "a" * 64,
            "parsed_output_hash": "",
            "blockers": ["structured_output_invalid_json"],
            "raw_secret": "must-not-persist",
        }
        record = build_structured_output_failure_record(
            receipt,
            org_id="org",
            project_id="project",
            run_id="run",
            case_id="case",
            created_at="2026-07-13T00:00:00Z",
        )
        self.assertEqual(record["record_type"], "structured_output_failure")
        self.assertNotIn("must-not-persist", json.dumps(record))
    def test_prompt_supersession_persists_as_hash_only_audit_record(self):
        current = "sha256:" + "a" * 64
        previous = "sha256:" + "b" * 64
        observation = validate_prompt_lineage(
            current_prompt_hash=current,
            supersedes_prompt_hash=previous,
            known_lineage={},
            maximum_lineage_depth=8,
        )
        record = build_result_record(
            observation,
            org_id="org-a2",
            project_id="project-a2",
            run_id="run-prompt-supersession",
            kind="prompt_supersession",
            judge_version="a2-prompt-lineage-v1",
        )
        self.assertTrue(observation["lineage_valid"])
        self.assertEqual(record["record_type"], "prompt_supersession")
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))
        self.assertNotIn(current, json.dumps(record))
        self.assertNotIn(previous, json.dumps(record))

    def test_ocr_failure_observation_persists_as_hash_only_audit_record(self):
        observation = run_optional_ocr_adapter(
            image_path="missing.png",
            adapter_id="offline-test",
            adapter_version_hash="sha256:" + "1" * 64,
            adapter=lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        )
        record = build_result_record(
            observation,
            org_id="org-a2",
            project_id="project-a2",
            run_id="run-ocr-failure",
            kind="ocr_observation",
            judge_version="a2-ocr-contract-v1",
        )
        self.assertEqual(observation["state"], "failed")
        self.assertEqual(record["record_type"], "ocr_observation")
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))
        self.assertNotIn("provider unavailable", json.dumps(record))
        self.assertTrue(record["metadata"]["raw_payload_not_recorded"])

    def test_manifest_fixture_matches_builder(self):
        grade_report = load_json(GRADE_REPORT)
        release_gate = load_json(RELEASE_GATE)
        release_unblock_checklist = load_json(RELEASE_UNBLOCK_CHECKLIST)
        scenario_pack = load_json(SCENARIO_PACK)
        scenario_selection = load_json(SCENARIO_SELECTION)
        run_fixtures = [load_json(path) for path in sorted(RUN_DIR.glob("*.json"))]

        actual = build_result_persistence_manifest(
            grade_report,
            release_gate,
            scenario_pack,
            scenario_selection_report=scenario_selection,
            release_unblock_checklist_report=release_unblock_checklist,
            run_fixtures=run_fixtures,
            source_refs={
                "grade_report": "fixtures/a2/results/a2_g3_grade_results.json",
                "release_gate": "fixtures/a2/results/a2_release_gate_report.json",
                "scenario_pack": "packages/scenarios/a2_g3_full_pack.json",
                "scenario_selection": "fixtures/a2/results/a2_scenario_selection_report.json",
                "regression_promotion_queue": "fixtures/a2/results/a2_regression_promotion_queue.json",
                "release_unblock_checklist": "fixtures/a2/results/a2_release_unblock_checklist.json",
            },
        )

        self.assertEqual(actual, load_json(MANIFEST_FIXTURE))

    def test_manifest_has_required_audit_fields_and_record_types(self):
        manifest = load_json(MANIFEST_FIXTURE)
        schema = load_json(MANIFEST_SCHEMA)
        records = manifest["records"]

        self.assertEqual(schema["properties"]["schema_version"]["const"], manifest["schema_version"])
        self.assertEqual(manifest["record_count"], len(records))
        self.assertEqual(manifest["tenant_id"], manifest["org"])
        self.assertEqual(
            manifest["source_refs"]["regression_promotion_queue"],
            "fixtures/a2/results/a2_regression_promotion_queue.json",
        )
        self.assertEqual(
            manifest["source_refs"]["release_unblock_checklist"],
            "fixtures/a2/results/a2_release_unblock_checklist.json",
        )
        self.assertEqual(
            manifest["record_type_counts"],
            {
                "judge_result": 160,
                "release_gate": 1,
                "release_unblock_checklist": 1,
                "scenario_selection": 1,
            },
        )
        self.assertEqual({record["record_type"] for record in records}, set(manifest["record_type_counts"]))

        for record in records:
            with self.subTest(record_type=record["record_type"], case=record["case"], judge=record["judge_id"]):
                self.assertLessEqual(REQUIRED_RECORD_FIELDS, set(record))
                self.assertEqual(record["tenant_id"], manifest["tenant_id"])
                self.assertEqual(record["org"], manifest["org"])
                self.assertEqual(record["project"], manifest["project"])
                self.assertEqual(record["run"], manifest["run"])
                self.assertRegex(record["policy_hash"], HASH_RE)
                self.assertRegex(record["input_hash"], HASH_RE)
                self.assertRegex(record["output_hash"], HASH_RE)
                self.assertNotIn("evidence", record)

    def test_release_gate_and_scenario_selection_records_are_public_summaries(self):
        manifest = load_json(MANIFEST_FIXTURE)
        release_gate = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        scenario_selection = next(
            record for record in manifest["records"] if record["record_type"] == "scenario_selection"
        )
        release_unblock = next(
            record for record in manifest["records"] if record["record_type"] == "release_unblock_checklist"
        )

        self.assertEqual(release_gate["case"], "release-gate")
        self.assertEqual(release_gate["decision"], "block")
        self.assertEqual(release_gate["judge_id"], "release_policy_engine")
        self.assertEqual(release_unblock["case"], "release-unblock-checklist")
        self.assertEqual(release_unblock["judge_id"], "release_unblock_checklist")
        self.assertEqual(release_unblock["overall_status"], "blocked")
        self.assertEqual(release_unblock["blocked_gate_count"], 3)
        self.assertTrue(release_unblock["private_evidence_required"])
        self.assertEqual(scenario_selection["case"], "scenario-selection")
        self.assertEqual(scenario_selection["selection_id"], "a2_enterprise_saas_prod_selection")
        self.assertEqual(scenario_selection["selected_count"], 12)
        self.assertTrue(scenario_selection["selected"])

    def test_manifest_does_not_persist_private_refs_raw_evidence_or_secrets(self):
        manifest_text = MANIFEST_FIXTURE.read_text(encoding="utf-8")

        self.assertNotIn("docs/evidence/private_refs", manifest_text)
        self.assertNotIn("private_input_ref", manifest_text)
        self.assertNotIn("final_response_excerpt", manifest_text)
        self.assertNotIn("tool_sequence", manifest_text)
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(manifest_text), pattern.pattern)

    def test_release_policy_waiver_audit_enters_manifest_as_public_summary(self):
        release_gate = _release_gate_with_policy_waiver()
        manifest = build_result_persistence_manifest(
            {"schema_version": "a2.grade_results.v1", "report_id": "unit", "dataset_id": "unit", "grade_results": []},
            release_gate,
            {"schema_version": "a2.scenario_pack.v1", "scenarios": []},
            created_at="2026-07-07T00:00:00Z",
        )
        release_gate_record = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        audit = release_gate_record["release_policy_audit"]

        self.assertEqual(audit["decision"], "pass")
        self.assertEqual(audit["waiver_summary"]["applied_count"], 1)
        self.assertEqual(audit["waiver_summary"]["waived_blocking_count"], 1)
        self.assertNotIn("raw_note", audit["waiver_summary"])
        self.assertEqual(audit["applied_waivers"][0]["waiver_id"], "wv-prod-safety")
        self.assertEqual(audit["applied_waivers"][0]["approval_id"], "approval-prod-safety")
        self.assertTrue(audit["applied_waivers"][0]["reason_present"])
        self.assertRegex(audit["applied_waivers"][0]["reason_hash"], HASH_RE)
        self.assertEqual(audit["applied_waivers"][0]["evidence_ref_count"], 1)
        self.assertRegex(audit["applied_waivers"][0]["evidence_ref_hashes"][0], HASH_RE)
        self.assertEqual(audit["waived_violations"][0]["rule_id"], "prod_no_safety_policy_violations")
        self.assertEqual(audit["waived_violations"][0]["observed"]["failure_class"], "unsafe_or_policy_violation")

        record_text = json.dumps(release_gate_record, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("raw_payload", record_text)
        self.assertNotIn("api_key", record_text)
        self.assertNotIn("Reviewed private waiver reason", record_text)
        self.assertNotIn("secret-test-value", record_text)

    def test_release_policy_saas_surface_audit_persists_public_safe_summary(self):
        release_gate = _release_gate_with_saas_surface_violations()
        manifest = build_result_persistence_manifest(
            {"schema_version": "a2.grade_results.v1", "report_id": "unit", "dataset_id": "unit", "grade_results": []},
            release_gate,
            {"schema_version": "a2.scenario_pack.v1", "scenarios": []},
            created_at="2026-07-07T00:00:00Z",
        )
        release_gate_record = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        audit = release_gate_record["release_policy_audit"]

        self.assertEqual(
            audit["saas_surface_metrics"],
            {
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "api_key_boundary_violations": 1,
                "server_side_grading_stale": 1,
            },
        )
        self.assertEqual(len(audit["active_violations"]), 4)
        active_by_metric = {
            violation["observed"]["metric"]: violation for violation in audit["active_violations"]
        }
        self.assertEqual(active_by_metric["api_key_boundary_violations"]["mode"], "blocking")
        self.assertEqual(active_by_metric["api_key_boundary_violations"]["severity"], "critical")
        self.assertEqual(active_by_metric["usage_quota_blocked"]["owner_role"], "billing_admin")
        self.assertEqual(active_by_metric["server_side_grading_stale"]["dashboard_label"], "Server-side grading stale")
        self.assertNotIn("raw_account_payload", audit["saas_surface_metrics"])

        jsonl_record = build_result_record(
            {
                "schema_version": "a2.internal_service_response.v1",
                "endpoint": "/internal/release-policy/evaluate",
                "ok": True,
                "status_code": 200,
                "result": release_gate,
            },
            org_id="org_demo",
            project_id="project_enterprise",
            run_id="run_demo",
            kind="release_policy",
            judge_version="a2-judge-service-0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={"authorization": "Bearer" + " secret-test-value-1234"},
            created_at="2026-07-07T00:00:00Z",
        )
        jsonl_audit = jsonl_record["output_summary"]["release_policy_audit"]
        self.assertEqual(jsonl_audit["saas_surface_metrics"], audit["saas_surface_metrics"])
        self.assertEqual(len(jsonl_audit["active_violations"]), 4)

        record_text = json.dumps({"release_gate": release_gate_record, "jsonl": jsonl_record}, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("raw_account_payload", record_text)
        self.assertNotIn("raw_request_body", record_text)
        self.assertNotIn("should-not-persist", record_text)
        self.assertNotIn("Bearer", record_text)
        self.assertNotIn("ashr_live_", record_text)
        self.assertNotIn("secret-test-value", record_text)

    def test_jsonl_ready_record_keeps_hashes_without_raw_payload_or_private_refs(self):
        record = build_result_record(
            {
                "endpoint": "/internal/judge/case",
                "scenario_id": "A2-S048",
                "case_id": "secret-case",
                "passed": False,
                "primary_failure_class": "unsafe_or_policy_violation",
                "final_response": "API key is " + "ashr_live_" + "1234567890abcdef.",
            },
            org_id="org_demo",
            project_id="proj_demo",
            run_id="run_demo",
            case_id="secret-case",
            kind="judge_result",
            judge_version="0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={"authorization": "Bearer" + " token-value", "prompt": "raw prompt"},
            evidence_refs=["docs/evidence/private_refs/raw.json"],
            created_at="2026-07-07T00:00:00Z",
        )
        record_text = json.dumps(record, sort_keys=True)

        self.assertRegex(record["input_hash"], HASH_RE)
        self.assertEqual(record["tenant_id"], "org_demo")
        self.assertRegex(record["output_hash"], HASH_RE)
        self.assertRegex(record["evidence_ref_hash"], HASH_RE)
        self.assertNotIn("payload", record)
        self.assertNotIn("evidence_refs", record)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("ashr_live_", record_text)
        self.assertNotIn("Bearer", record_text)

    def test_jsonl_ready_release_policy_record_keeps_public_waiver_audit_only(self):
        record = build_result_record(
            {
                "schema_version": "a2.internal_service_response.v1",
                "endpoint": "/internal/release-policy/evaluate",
                "ok": True,
                "status_code": 200,
                "result": _release_gate_with_policy_waiver(),
            },
            org_id="org_demo",
            project_id="project_enterprise",
            run_id="run_demo",
            kind="release_policy",
            judge_version="a2-judge-service-0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={
                "waivers": [
                    {
                        "evidence_ref": "docs/evidence/private_refs/service-waiver.json",
                        "token": "secret-test-value-1234",
                    }
                ]
            },
            created_at="2026-07-07T00:00:00Z",
        )
        audit = record["output_summary"]["release_policy_audit"]
        applied = audit["applied_waivers"][0]

        self.assertEqual(record["output_summary"]["endpoint"], "/internal/release-policy/evaluate")
        self.assertEqual(audit["policy_id"], "release_policy_prod_strict")
        self.assertEqual(applied["waived_rule_id"], "prod_no_safety_policy_violations")
        self.assertRegex(applied["reason_hash"], HASH_RE)
        self.assertRegex(record["input_hash"], HASH_RE)
        self.assertRegex(record["output_hash"], HASH_RE)
        record_text = json.dumps(record, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("Reviewed private waiver reason", record_text)
        self.assertNotIn('"raw_payload"', record_text)
        self.assertNotIn("api_key", record_text)
        self.assertNotIn("secret-test-value", record_text)


def _release_gate_with_policy_waiver() -> dict:
    return {
        "schema_version": "a2.release_gate.v1",
        "release_candidate": {"id": "agent-v42", "profile": "strict-commercial"},
        "decision": "pass",
        "exit_code": 0,
        "risk_score": 10,
        "blocking_gate_count": 0,
        "evidence_blocker_count": 0,
        "warning_count": 0,
        "ready_for_commercial_gate": True,
        "policy_evaluation": {
            "schema_version": "a2.release_policy_evaluation.v1",
            "policy_id": "release_policy_prod_strict",
            "policy_version": "2026-07-07.1",
            "policy_hash": stable_hash({"policy": "unit"}),
            "project_id": "project_enterprise",
            "environment": "prod",
            "release_candidate_id": "agent-v42",
            "decision": "pass",
            "blocking_violation_count": 0,
            "non_blocking_violation_count": 0,
            "waived_violation_count": 1,
            "waiver_summary": {
                "submitted_count": 1,
                "applied_count": 1,
                "unapplied_count": 0,
                "waived_blocking_count": 1,
                "waived_non_blocking_count": 0,
                "active_blocking_count": 0,
                "active_non_blocking_count": 0,
                "raw_note": "do not persist",
            },
            "applied_waivers": [
                {
                    "waiver_id": "wv-prod-safety",
                    "approval_id": "approval-prod-safety",
                    "status": "approved",
                    "reviewer": "release-manager",
                    "reason": "Reviewed private waiver reason with secret-test-value-1234.",
                    "evidence_ref": "docs/evidence/private_refs/reviewed-waiver.json",
                    "waived_rule_id": "prod_no_safety_policy_violations",
                    "waived_mode": "blocking",
                    "waived_severity": "critical",
                    "waived_type": "failure_class_threshold",
                    "raw_payload": {"api_key": "secret-test-value-1234"},
                }
            ],
            "waived_violations": [
                {
                    "rule_id": "prod_no_safety_policy_violations",
                    "type": "failure_class_threshold",
                    "mode": "blocking",
                    "severity": "critical",
                    "passed": False,
                    "summary": "Production releases cannot include safety or policy violations.",
                    "observed": {
                        "failure_class": "unsafe_or_policy_violation",
                        "count": 1,
                        "rate": 1.0,
                        "raw_payload": "do not persist",
                    },
                    "threshold": {"max_count": 0},
                    "waiver": {
                        "waiver_id": "wv-prod-safety",
                        "approval_id": "approval-prod-safety",
                        "status": "approved",
                        "reviewer": "release-manager",
                        "reason": "Reviewed private waiver reason with docs/evidence/private_refs/reviewed-waiver.json.",
                        "evidence_refs": ["docs/evidence/private_refs/reviewed-waiver.json"],
                        "api_key": "secret-test-value-1234",
                    },
                }
            ],
            "unapplied_waivers": [{"raw_payload": {"api_key": "secret-test-value-1234"}}],
        },
    }


def _release_gate_with_saas_surface_violations() -> dict:
    return {
        "schema_version": "a2.release_gate.v1",
        "release_candidate": {"id": "agent-v43", "profile": "strict-commercial"},
        "decision": "block",
        "exit_code": 2,
        "risk_score": 95,
        "blocking_gate_count": 4,
        "evidence_blocker_count": 0,
        "warning_count": 0,
        "ready_for_commercial_gate": False,
        "policy_evaluation": {
            "schema_version": "a2.release_policy_evaluation.v1",
            "policy_id": "release_policy_prod_strict",
            "policy_version": "2026-07-07.1",
            "policy_hash": stable_hash({"policy": "unit-saas-surface"}),
            "project_id": "project_enterprise",
            "environment": "prod",
            "release_candidate_id": "agent-v43",
            "decision": "block",
            "blocking_violation_count": 4,
            "non_blocking_violation_count": 0,
            "waived_violation_count": 0,
            "metrics": {
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "api_key_boundary_violations": 1,
                "server_side_grading_stale": 1,
                "raw_account_payload": "should-not-persist",
            },
            "violations": [
                _saas_metric_violation(
                    "prod_usage_quota_available",
                    "usage_quota_blocked",
                    "blocking",
                    "high",
                    "billing_admin",
                    "Usage quota blocks release evaluation.",
                    "Usage quota blocked",
                    45,
                ),
                _saas_metric_violation(
                    "prod_no_api_key_boundary_violations",
                    "api_key_boundary_violations",
                    "blocking",
                    "critical",
                    "security_admin",
                    "Release boundary leaked credential handling.",
                    "API key boundary violation",
                    45,
                ),
                _saas_metric_violation(
                    "prod_trust_page_publishable",
                    "trust_publishability_blocked",
                    "blocking",
                    "high",
                    "release_manager",
                    "Trust page is not publishable for enterprise review.",
                    "Trust publishability blocked",
                    25,
                ),
                _saas_metric_violation(
                    "prod_server_side_grading_current",
                    "server_side_grading_stale",
                    "blocking",
                    "high",
                    "evaluation_owner",
                    "Server-side grading evidence is stale.",
                    "Server-side grading stale",
                    25,
                ),
            ],
        },
    }


def _saas_metric_violation(
    rule_id: str,
    metric: str,
    mode: str,
    severity: str,
    owner_role: str,
    business_impact: str,
    dashboard_label: str,
    risk_weight: int,
) -> dict:
    return {
        "rule_id": rule_id,
        "type": "metric_threshold",
        "mode": mode,
        "severity": severity,
        "passed": False,
        "summary": f"{metric} failed == 0.",
        "owner_role": owner_role,
        "business_impact": business_impact,
        "dashboard_label": dashboard_label,
        "risk_weight": risk_weight,
        "waiver_eligible": False,
        "observed": {
            "metric": metric,
            "value": 1,
            "raw_request_body": "should-not-persist",
        },
        "threshold": {"operator": "==", "threshold": 0},
        "evidence_refs": ["docs/evidence/private_refs/saas-surface.json"],
        "raw_payload": {"token": "ashr" + "_live_should_not_persist"},
    }


if __name__ == "__main__":
    unittest.main()
