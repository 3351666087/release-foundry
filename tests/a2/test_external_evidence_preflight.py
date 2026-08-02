import json
import tempfile
from pathlib import Path

from scripts.a2_external_evidence_preflight import build_preflight


def _write_json(directory: Path, name: str, payload: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _build_with_payloads(
    directory: Path,
    *,
    evidence: object,
    case_book: object | None = None,
    replay: object | None = None,
    commercial: object | None = None,
) -> dict:
    return build_preflight(
        evidence_readiness_path=_write_json(directory, "evidence.json", evidence),
        case_book_path=_write_json(directory, "case-book.json", case_book or {}),
        regression_replay_path=_write_json(directory, "replay.json", replay or {}),
        commercial_readiness_path=_write_json(directory, "commercial.json", commercial or {}),
    )


def test_preflight_rejects_truthy_strings_for_authoritative_gates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        preflight = _build_with_payloads(
            Path(tmp_dir),
            evidence={
                "releasefoundry_public_merge_gate": {
                    "safe_to_mark_c3_met": "false",
                    "expected_reviewed_observation_count": 6,
                    "reviewed_public_observation_count": 6,
                },
                "semantic_live_merge_gate": {
                    "safe_to_mark_c4_met": "false",
                    "expected_reviewed_observation_count": 6,
                    "reviewed_live_observation_count": 6,
                },
            },
            case_book={"maturity_gate": {"ready": "false"}},
            replay={"maturity_gate": {"ready": "false"}},
        )

    assert preflight["gate_summary"]["C3"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C4"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C5"]["case_book_ready"] is False
    assert preflight["gate_summary"]["C5"]["replay_ready"] is False
    assert len(preflight["next_actions"]) == 3


def test_preflight_fails_closed_for_malformed_gate_objects_and_counts():
    with tempfile.TemporaryDirectory() as tmp_dir:
        preflight = _build_with_payloads(
            Path(tmp_dir),
            evidence={
                "releasefoundry_public_merge_gate": "false",
                "semantic_live_merge_gate": None,
                "releasefoundry_grading_preflight": "false",
                "semantic_judge_preflight": None,
            },
            case_book={
                "maturity_gate": {
                    "ready": True,
                    "current_regression_case_count": "3",
                    "target_regression_case_count": True,
                    "gaps": "none",
                }
            },
            replay={"maturity_gate": None},
            commercial={"gate_status": "false"},
        )

    assert preflight["gate_summary"]["C3"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C3"]["commercial_status"] == "unknown"
    assert preflight["gate_summary"]["C3"]["missing_reviewed_observations"] == 0
    assert preflight["gate_summary"]["C4"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C5"]["case_book_ready"] is True
    assert preflight["gate_summary"]["C5"]["replay_ready"] is False
    assert preflight["gate_summary"]["C5"]["current_regression_cases"] == 0
    assert preflight["gate_summary"]["C5"]["target_regression_cases"] == 0
    assert preflight["gate_summary"]["C5"]["gaps"] == []


def test_preflight_rejects_non_object_top_level_payloads():
    with tempfile.TemporaryDirectory() as tmp_dir:
        preflight = _build_with_payloads(
            Path(tmp_dir),
            evidence=["not", "an", "object"],
            case_book="false",
            replay=None,
            commercial=[{"gate": "C3", "status": "met"}],
        )

    assert preflight["gate_summary"]["C3"]["commercial_status"] == "unknown"
    assert preflight["gate_summary"]["C3"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C4"]["safe_to_mark_met"] is False
    assert preflight["gate_summary"]["C5"]["case_book_ready"] is False
    assert preflight["gate_summary"]["C5"]["replay_ready"] is False
