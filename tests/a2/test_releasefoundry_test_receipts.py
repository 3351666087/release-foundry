from copy import deepcopy

import pytest

from scripts.a2_verify_releasefoundry_test_receipts import (
    _polling_finished,
    poll_releasefoundry_run_receipt,
)
from services.judge.releasefoundry_test_receipts import (
    ReleaseFoundryTestReceiptError,
    assert_public_releasefoundry_test_terminal_receipt_safe,
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)


CASE_MAP = {
    "releasefoundry-test-pass": "sample-pass",
    "releasefoundry-test-fail": "sample-fail",
}


def _run() -> dict:
    return {
        "id": 42,
        "dataset": 7,
        "result": {
            "status": "completed_with_failures",
            "judge_version": "releasefoundry-grader-v1",
            "aggregate_metrics": {
                "total_tests": 2,
                "tests_passed": 1,
                "tests_failed": 1,
            },
            "tests": [
                {
                    "test_id": "releasefoundry-test-pass",
                    "status": "completed",
                    "started_at": "2026-07-26T01:00:00Z",
                    "completed_at": "2026-07-26T01:00:01Z",
                    "action_results": [
                        {
                            "actor": "agent",
                            "action_type": "text",
                            "action_index": 1,
                            "actual_response": {"content": "safe answer"},
                            "match_status": "similar",
                            "semantic_similarity": 0.95,
                            "llm_judgment": {
                                "verdict": "match",
                                "reason": "The answer is correct.",
                            },
                        }
                    ],
                },
                {
                    "test_id": "releasefoundry-test-fail",
                    "status": "failed",
                    "started_at": "2026-07-26T01:00:02+00:00",
                    "completed_at": "2026-07-26T01:00:03+00:00",
                    "action_results": [
                        {
                            "actor": "agent",
                            "action_type": "tool_call",
                            "action_index": 1,
                            "tool_calls": [
                                {
                                    "actual": {
                                        "tool_name": "weather",
                                        "arguments": {"city": "wrong"},
                                    },
                                    "expected": {
                                        "tool_name": "weather",
                                        "arguments": {"city": "right"},
                                    },
                                    "match_status": "mismatch",
                                    "argument_comparison": {
                                        "status": "mismatch",
                                        "actual_args": {"city": "wrong"},
                                        "expected_args": {"city": "right"},
                                        "exact_match": False,
                                    },
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    }


def _receipt(run: dict | None = None, **kwargs) -> dict:
    return build_releasefoundry_test_terminal_receipt(
        run or _run(),
        case_map=CASE_MAP,
        expected_dataset_id=7,
        **kwargs,
    )


def test_verifies_completed_and_failed_tests_individually():
    receipt = _receipt()

    assert receipt["verification_state"] == "verified"
    assert receipt["run_result_terminal_verified"] is True
    assert receipt["server_grading_lifecycle_verified"] is True
    assert receipt["all_expected_tests_terminal_scoring_verified"] is True
    assert receipt["exact_test_set_verified"] is True
    assert receipt["verified_test_count"] == 2
    assert receipt["nonterminal_test_count"] == 0
    assert receipt["aggregate_marker_used_as_acceptance_authority"] is False
    assert [item["terminal_status"] for item in receipt["tests"]] == [
        "completed",
        "failed",
    ]
    assert all(item["terminal_scoring_verified"] for item in receipt["tests"])
    assert all(item["response_evidence_verified"] for item in receipt["tests"])
    assert receipt["tests"][0]["grading_signal_types"] == [
        "action_llm_judgment"
    ]
    assert receipt["tests"][1]["grading_signal_types"] == [
        "tool_argument_comparison"
    ]


def test_accepts_observed_acceptable_and_legacy_object_grading_shapes():
    run = _run()
    run["result"]["tests"][0]["action_results"][0]["llm_judgment"][
        "verdict"
    ] = "acceptable"
    comparison = run["result"]["tests"][1]["action_results"][0][
        "tool_calls"
    ][0]["argument_comparison"]
    comparison.clear()
    comparison.update(
        {
            "different": {
                "city": {
                    "actual": "wrong",
                    "expected": "right",
                }
            },
            "extra": {},
            "matching": {},
            "missing": {},
        }
    )

    receipt = _receipt(run)

    assert receipt["verification_state"] == "verified"
    assert receipt["tests"][0]["grading_signal_types"] == [
        "action_llm_judgment"
    ]
    assert receipt["tests"][1]["grading_signal_types"] == [
        "tool_argument_comparison"
    ]


def test_run_level_status_must_be_terminal():
    run = _run()
    run["result"]["status"] = "running"

    receipt = _receipt(run)

    assert receipt["verification_state"] == "blocked"
    assert receipt["run_result_terminal_verified"] is False
    assert receipt["all_expected_tests_terminal_scoring_verified"] is False
    assert "run_result_status_not_terminal" in receipt["blockers"]


def test_optional_grading_status_is_a_lifecycle_veto():
    run = _run()
    run["result"]["grading_status"] = "pending"

    receipt = _receipt(run)

    assert receipt["grading_status_present"] is True
    assert receipt["grading_status_terminal_verified"] is False
    assert receipt["server_grading_lifecycle_verified"] is False
    assert receipt["all_expected_tests_terminal_scoring_verified"] is False
    assert "grading_status_not_terminal" in receipt["blockers"]


def test_conflicting_grading_statuses_fail_closed():
    run = _run()
    run["grading_status"] = "completed"
    run["result"]["grading_status"] = "failed"

    receipt = _receipt(run)

    assert receipt["verification_state"] == "blocked"
    assert "grading_status_ambiguous" in receipt["blockers"]


def test_run_level_completed_marker_cannot_hide_running_test():
    run = _run()
    run["result"]["status"] = "completed"
    run["result"]["tests"][1]["status"] = "running"

    receipt = _receipt(run)

    assert receipt["verification_state"] == "blocked"
    assert receipt["nonterminal_test_count"] == 1
    assert receipt["all_expected_tests_terminal_scoring_verified"] is False
    assert "test_status_not_scoring_terminal" in receipt["blockers"]


def test_missing_expected_test_blocks_receipt():
    run = _run()
    run["result"]["tests"].pop()

    receipt = _receipt(run)

    assert receipt["missing_test_count"] == 1
    assert "test_missing" in receipt["blockers"]


def test_duplicate_expected_test_blocks_receipt():
    run = _run()
    run["result"]["tests"].append(deepcopy(run["result"]["tests"][0]))

    receipt = _receipt(run)

    assert receipt["duplicate_test_count"] == 1
    assert "test_id_duplicate" in receipt["blockers"]


def test_unexpected_test_blocks_exact_run_binding():
    run = _run()
    extra = deepcopy(run["result"]["tests"][0])
    extra["test_id"] = "releasefoundry-test-extra"
    run["result"]["tests"].append(extra)

    receipt = _receipt(run)

    assert receipt["unexpected_test_count"] == 1
    assert receipt["exact_test_set_verified"] is False
    assert "unexpected_test_present" in receipt["blockers"]


def test_case_id_never_falls_back_for_missing_test_id():
    run = _run()
    run["result"]["tests"][0].pop("test_id")
    run["result"]["tests"][0]["case_id"] = "releasefoundry-test-pass"

    receipt = _receipt(run)

    assert receipt["unidentified_test_count"] == 1
    assert receipt["missing_test_count"] == 1
    assert "test_id_missing_or_invalid" in receipt["blockers"]
    assert "test_missing" in receipt["blockers"]


def test_non_object_test_entry_fails_closed():
    run = _run()
    run["result"]["tests"].append("not-a-test-object")

    receipt = _receipt(run)

    assert receipt["malformed_test_count"] == 1
    assert receipt["valid_test_object_count"] == 2
    assert "test_entry_not_object" in receipt["blockers"]


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("started_at", "", "test_terminal_timestamps_missing_or_invalid"),
        (
            "completed_at",
            "not-a-date",
            "test_terminal_timestamps_missing_or_invalid",
        ),
        ("action_results", [], "test_response_evidence_missing"),
    ],
)
def test_incomplete_per_test_evidence_blocks_receipt(field, value, blocker):
    run = _run()
    run["result"]["tests"][0][field] = value

    receipt = _receipt(run)

    assert receipt["verification_state"] == "blocked"
    assert blocker in receipt["blockers"]


def test_none_or_empty_response_does_not_count_as_evidence():
    for value in (None, {}, [], "  "):
        run = _run()
        run["result"]["tests"][0]["action_results"][0][
            "actual_response"
        ] = value

        receipt = _receipt(run)

        assert receipt["tests"][0]["response_evidence_verified"] is False
        assert "test_response_evidence_missing" in receipt["blockers"]


def test_client_side_match_fields_do_not_prove_server_grading():
    run = _run()
    action = run["result"]["tests"][0]["action_results"][0]
    action.pop("llm_judgment")

    receipt = _receipt(run)

    assert action["match_status"] == "similar"
    assert action["semantic_similarity"] == 0.95
    assert receipt["tests"][0]["server_grading_signal_verified"] is False
    assert "test_server_grading_signal_missing" in receipt["blockers"]


def test_empty_llm_judgment_does_not_count_as_server_grading():
    run = _run()
    run["result"]["tests"][0]["action_results"][0]["llm_judgment"] = {}

    receipt = _receipt(run)

    assert receipt["tests"][0]["server_grading_signal_verified"] is False
    assert "test_server_grading_signal_missing" in receipt["blockers"]


def test_incomplete_argument_comparison_does_not_count_as_server_grading():
    run = _run()
    comparison = run["result"]["tests"][1]["action_results"][0]["tool_calls"][
        0
    ]["argument_comparison"]
    comparison.clear()
    comparison["status"] = "exact"

    receipt = _receipt(run)

    assert receipt["tests"][1]["server_grading_signal_verified"] is False
    assert "test_server_grading_signal_missing" in receipt["blockers"]


def test_coherence_requires_score_and_nonempty_diagnostic():
    run = _run()
    action = run["result"]["tests"][0]["action_results"][0]
    action.pop("llm_judgment")
    run["result"]["tests"][0]["coherence"] = {
        "score": 1.0,
        "summary": "",
        "issues": [],
    }

    receipt = _receipt(run)

    assert receipt["tests"][0]["server_grading_signal_verified"] is False
    assert "test_server_grading_signal_missing" in receipt["blockers"]


def test_reversed_terminal_timestamps_block_receipt():
    run = _run()
    run["result"]["tests"][0]["completed_at"] = "2026-07-26T00:59:59Z"

    receipt = _receipt(run)

    assert "test_terminal_timestamps_missing_or_invalid" in receipt["blockers"]


def test_native_media_output_and_complete_coherence_are_verifiable():
    run = _run()
    run["result"]["tests"][0]["action_results"] = [
        {
            "actor": "agent",
            "action_type": "audio",
            "action_index": 1,
            "output_path": "private/audio.wav",
        }
    ]
    run["result"]["tests"][0]["coherence"] = {
        "score": 1.0,
        "summary": "The audio output is coherent.",
        "issues": [],
    }

    receipt = _receipt(run)

    first = receipt["tests"][0]
    assert first["response_evidence_verified"] is True
    assert first["response_evidence_kinds"] == ["agent_output"]
    assert first["server_grading_signal_verified"] is True
    assert first["grading_signal_types"] == ["test_coherence"]
    assert first["terminal_scoring_verified"] is True


def test_aggregate_total_mismatch_is_a_veto():
    run = _run()
    run["result"]["aggregate_metrics"]["total_tests"] = 999

    receipt = _receipt(run)

    assert receipt["aggregate_total_marker_present"] is True
    assert receipt["aggregate_total_marker_consistent"] is False
    assert receipt["verification_state"] == "blocked"
    assert "aggregate_total_mismatch" in receipt["blockers"]


def test_dataset_mismatch_blocks_receipt():
    run = _run()
    run["dataset"] = 8

    receipt = _receipt(run)

    assert receipt["verification_state"] == "blocked"
    assert "run_dataset_id_mismatch" in receipt["blockers"]


def test_operator_attested_judge_version_cannot_complete_receipt():
    run = _run()
    run["result"].pop("judge_version")

    receipt = _receipt(run, expected_judge_version="operator-known-v2")

    assert receipt["all_expected_tests_terminal_scoring_verified"] is True
    assert receipt["verification_state"] == "blocked"
    assert receipt["judge_version_verified"] is False
    assert (
        receipt["judge_version_source"]
        == "operator_attested_not_server_observed"
    )
    assert "judge_version_not_server_observed" in receipt["blockers"]


def test_missing_judge_version_blocks_complete_receipt_but_not_terminal_facts():
    run = _run()
    run["result"].pop("judge_version")

    receipt = _receipt(run)

    assert receipt["all_expected_tests_terminal_scoring_verified"] is True
    assert receipt["receipt_complete"] is False
    assert receipt["verification_state"] == "blocked"
    assert "judge_version_missing" in receipt["blockers"]


def test_conflicting_server_judge_versions_fail_closed():
    run = _run()
    run["metadata"] = {"grader_version": "different-version"}

    receipt = _receipt(run)

    assert receipt["judge_version_candidate_count"] == 2
    assert receipt["judge_version_verified"] is False
    assert receipt["observed_judge_version"] == ""
    assert "judge_version_ambiguous" in receipt["blockers"]


def test_server_judge_version_mismatch_blocks_receipt():
    receipt = _receipt(expected_judge_version="different-version")

    assert receipt["verification_state"] == "blocked"
    assert receipt["judge_version_source"] == "server_observed"
    assert "judge_version_mismatch" in receipt["blockers"]


def test_generic_model_version_does_not_satisfy_judge_provenance():
    run = _run()
    run["result"].pop("judge_version")
    run["result"]["model_version"] = "candidate-model-v1"

    receipt = _receipt(run)

    assert receipt["observed_judge_version"] == ""
    assert receipt["judge_version_verified"] is False
    assert "judge_version_missing" in receipt["blockers"]


def test_public_receipt_removes_raw_identifiers_hashes_content_and_timestamps():
    private = _receipt()

    public = public_releasefoundry_test_terminal_receipt(private)
    rendered = str(public)

    assert public["public_safe"] is True
    assert public["raw_releasefoundry_identifiers_included"] is False
    assert public["raw_payload_hashes_included"] is False
    assert public["public_case_ids_included"] is True
    assert "run_id" not in public
    assert all("test_id" not in item for item in public["tests"])
    assert all("started_at" not in item for item in public["tests"])
    assert all("completed_at" not in item for item in public["tests"])
    assert "safe answer" not in rendered
    assert "weather" not in rendered
    assert "releasefoundry-test-pass" not in rendered
    assert "sha256:" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "not-public"},
        {"nested": {"authorization": "redacted"}},
        {"note": "Bearer abcdefghijklmnop"},
        {"note": "https://example.test/file?X-Amz-Signature=private"},
        {"sdk_source": r"C:\Users\private\site-packages\releasefoundry"},
        {"sdk_source": "/home/private/site-packages/releasefoundry"},
    ],
)
def test_public_receipt_safety_scan_rejects_private_values(payload):
    with pytest.raises(ReleaseFoundryTestReceiptError):
        assert_public_releasefoundry_test_terminal_receipt_safe(payload)


def test_rejects_invalid_or_ambiguous_case_map():
    with pytest.raises(ReleaseFoundryTestReceiptError, match="case_map_missing"):
        build_releasefoundry_test_terminal_receipt(
            _run(),
            case_map={},
            expected_dataset_id=7,
        )
    with pytest.raises(ReleaseFoundryTestReceiptError, match="case_map_case_id_duplicate"):
        build_releasefoundry_test_terminal_receipt(
            _run(),
            case_map={"one": "same", "two": "same"},
            expected_dataset_id=7,
        )


def test_poller_stops_when_terminal_facts_are_known_but_provenance_is_blocked():
    run = _run()
    run["result"].pop("judge_version")
    receipt = _receipt(run)

    assert receipt["all_expected_tests_terminal_scoring_verified"] is True
    assert receipt["receipt_complete"] is False
    assert _polling_finished(receipt) is True


def test_poller_waits_for_missing_grading_evidence_but_stops_on_hard_blockers():
    run = _run()
    run["result"]["tests"][0]["action_results"][0].pop("llm_judgment")
    waiting = _receipt(run)

    assert waiting["nonterminal_test_count"] == 0
    assert waiting["receipt_complete"] is False
    assert _polling_finished(waiting) is False

    mismatched = _run()
    mismatched["dataset"] = 8
    assert _polling_finished(_receipt(mismatched)) is True


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _StaticClient:
    def __init__(self, run: dict) -> None:
        self.run = run
        self.timeout = 30.0
        self.calls = 0

    def get_run(self, run_id: int) -> dict:
        assert run_id == 42
        self.calls += 1
        return deepcopy(self.run)


def test_poll_deadline_is_strict_and_request_timeout_is_bounded():
    run = _run()
    run["result"]["status"] = "running"
    clock = _FakeClock()
    client = _StaticClient(run)

    receipt = poll_releasefoundry_run_receipt(
        client,
        run_id=42,
        case_map=CASE_MAP,
        expected_dataset_id=7,
        poll_seconds=10.0,
        timeout_seconds=1.0,
        request_timeout=30.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert client.calls == 1
    assert client.timeout == 1.0
    assert receipt["poll_count"] == 1
    assert receipt["poll_elapsed_ms"] == 1000
    assert receipt["verification_state"] == "blocked"
    assert "poll_timeout" in receipt["blockers"]


def test_poll_read_error_returns_redacted_blocked_receipt():
    class FailingClient:
        timeout = 30.0

        def get_run(self, run_id: int) -> dict:
            raise RuntimeError(f"private failure for run {run_id}")

    receipt = poll_releasefoundry_run_receipt(
        FailingClient(),
        run_id=42,
        case_map=CASE_MAP,
        expected_dataset_id=7,
        poll_seconds=1.0,
        timeout_seconds=5.0,
        request_timeout=2.0,
    )

    assert receipt["verification_state"] == "blocked"
    assert receipt["poll_error_type"] == "RuntimeError"
    assert "poll_read_error" in receipt["blockers"]
    assert "private failure" not in str(receipt)
