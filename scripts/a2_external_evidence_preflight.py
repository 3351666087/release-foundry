from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULT_DIR = Path("fixtures/a2/results")
DEFAULT_EVIDENCE_READINESS = DEFAULT_RESULT_DIR / "a2_evidence_readiness_report.json"
DEFAULT_CASE_BOOK = DEFAULT_RESULT_DIR / "a2_case_book.json"
DEFAULT_REGRESSION_REPLAY = DEFAULT_RESULT_DIR / "a2_regression_replay_report.json"
DEFAULT_COMMERCIAL_READINESS = DEFAULT_RESULT_DIR / "a2_commercial_readiness_report.json"


def build_preflight(
    *,
    evidence_readiness_path: str | Path = DEFAULT_EVIDENCE_READINESS,
    case_book_path: str | Path = DEFAULT_CASE_BOOK,
    regression_replay_path: str | Path = DEFAULT_REGRESSION_REPLAY,
    commercial_readiness_path: str | Path = DEFAULT_COMMERCIAL_READINESS,
) -> dict[str, Any]:
    evidence = _load_json(evidence_readiness_path)
    case_book = _load_json(case_book_path)
    replay = _load_json(regression_replay_path)
    commercial = _load_json(commercial_readiness_path)

    releasefoundry_gate = _mapping(evidence.get("releasefoundry_public_merge_gate"))
    semantic_gate = _mapping(evidence.get("semantic_live_merge_gate"))
    releasefoundry_preflight = _mapping(evidence.get("releasefoundry_grading_preflight"))
    semantic_preflight = _mapping(evidence.get("semantic_judge_preflight"))
    case_book_gate = _mapping(case_book.get("maturity_gate"))
    replay_gate = _mapping(replay.get("maturity_gate"))
    commercial_gates = _commercial_gates(commercial.get("gate_status"))

    return {
        "schema_version": "a2.external_evidence_preflight.v1",
        "preflight_id": "a2_external_evidence_preflight",
        "requires_network": False,
        "requires_releasefoundry_api_key": False,
        "reads_private_payloads": False,
        "writes_files": False,
        "public_inputs": [
            Path(evidence_readiness_path).as_posix(),
            Path(case_book_path).as_posix(),
            Path(regression_replay_path).as_posix(),
            Path(commercial_readiness_path).as_posix(),
        ],
        "environment_probe": {
            "releasefoundry_api_key_present": bool(os.environ.get("RELEASEFOUNDRY_LABS_API_KEY")),
            "value_redacted": True,
        },
        "gate_summary": {
            "C3": _c3_summary(releasefoundry_gate, releasefoundry_preflight, commercial_gates.get("C3", {})),
            "C4": _c4_summary(semantic_gate, semantic_preflight, commercial_gates.get("C4", {})),
            "C5": _c5_summary(case_book_gate, replay_gate, commercial_gates.get("C5", {})),
        },
        "private_input_refs": _private_input_refs(releasefoundry_preflight, semantic_preflight),
        "recommended_commands": {
            "real_api_evidence_refresh": [
                "python -B scripts/a2_refresh_real_api_evidence_index.py --label a2-g3-real-api-refresh",
                "python -B scripts/a2_regenerate_fixtures.py --write",
            ],
            "releasefoundry_grading": _string_list(releasefoundry_preflight.get("commands")),
            "semantic_judge": _string_list(semantic_preflight.get("commands")),
            "post_merge_verification": [
                "python -B scripts/a2_regenerate_fixtures.py --check",
                "python -B -m unittest discover -s tests/a2 -v",
            ],
        },
        "redaction_policy": _mapping(evidence.get("redaction_policy")),
        "next_actions": _next_actions(releasefoundry_gate, semantic_gate, case_book_gate, replay_gate),
        "metadata": {
            "deterministic": True,
            "purpose": "Summarize the safe C3/C4/C5 evidence workflow without reading keys or private payloads.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print an offline A2 C3/C4/C5 external-evidence preflight without reading private payloads."
    )
    parser.add_argument("--json", action="store_true", help="Print the full preflight as JSON.")
    parser.add_argument("--evidence-readiness", default=DEFAULT_EVIDENCE_READINESS.as_posix())
    parser.add_argument("--case-book", default=DEFAULT_CASE_BOOK.as_posix())
    parser.add_argument("--regression-replay", default=DEFAULT_REGRESSION_REPLAY.as_posix())
    parser.add_argument("--commercial-readiness", default=DEFAULT_COMMERCIAL_READINESS.as_posix())
    args = parser.parse_args()

    os.chdir(ROOT)
    preflight = build_preflight(
        evidence_readiness_path=Path(args.evidence_readiness),
        case_book_path=Path(args.case_book),
        regression_replay_path=Path(args.regression_replay),
        commercial_readiness_path=Path(args.commercial_readiness),
    )
    if args.json:
        print(json.dumps(preflight, indent=2))
    else:
        print(_text_summary(preflight))
    return 0


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    return _mapping(json.loads(resolved.read_text(encoding="utf-8")))


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _commercial_gates(value: Any) -> dict[str, dict[str, Any]]:
    gates: dict[str, dict[str, Any]] = {}
    if not isinstance(value, list):
        return gates
    for item in value:
        gate = _mapping(item)
        gate_id = gate.get("gate")
        if isinstance(gate_id, str):
            gates[gate_id] = gate
    return gates


def _strict_true(value: Any) -> bool:
    return value is True


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _string(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _c3_summary(
    releasefoundry_gate: dict[str, Any],
    releasefoundry_preflight: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    expected = _nonnegative_int(releasefoundry_gate.get("expected_reviewed_observation_count"))
    reviewed = _nonnegative_int(releasefoundry_gate.get("reviewed_public_observation_count"))
    return {
        "name": "Reviewed ReleaseFoundry grading calibration",
        "commercial_status": _string(commercial_gate.get("status"), "unknown"),
        "merge_status": _string(releasefoundry_gate.get("status"), "unknown"),
        "safe_to_mark_met": _strict_true(releasefoundry_gate.get("safe_to_mark_c3_met")),
        "reviewed_observations": reviewed,
        "expected_reviewed_observations": expected,
        "missing_reviewed_observations": max(0, expected - reviewed),
        "case_map_covers_all_calibration_cases": _strict_true(
            releasefoundry_preflight.get("case_map_covers_all_calibration_cases")
        ),
        "blocking_reason": _string(releasefoundry_gate.get("blocking_reason")),
    }


def _c4_summary(
    semantic_gate: dict[str, Any],
    semantic_preflight: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    expected = _nonnegative_int(semantic_gate.get("expected_reviewed_observation_count"))
    reviewed = _nonnegative_int(semantic_gate.get("reviewed_live_observation_count"))
    return {
        "name": "Audited semantic judge evidence",
        "commercial_status": _string(commercial_gate.get("status"), "unknown"),
        "merge_status": _string(semantic_gate.get("status"), "unknown"),
        "safe_to_mark_met": _strict_true(semantic_gate.get("safe_to_mark_c4_met")),
        "reviewed_live_observations": reviewed,
        "expected_reviewed_observations": expected,
        "missing_reviewed_observations": max(0, expected - reviewed),
        "offline_reference_only": _strict_true(semantic_preflight.get("offline_reference_only")),
        "covered_sdk_languages": _string_list(semantic_preflight.get("covered_sdk_languages")),
        "blocking_reason": _string(semantic_gate.get("blocking_reason")),
    }


def _c5_summary(
    case_book_gate: dict[str, Any],
    replay_gate: dict[str, Any],
    commercial_gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": "Reviewed disagreement regression maturity",
        "commercial_status": _string(commercial_gate.get("status"), "unknown"),
        "case_book_status": _string(case_book_gate.get("status"), "unknown"),
        "case_book_ready": _strict_true(case_book_gate.get("ready")),
        "replay_ready": _strict_true(replay_gate.get("ready")),
        "current_regression_cases": _nonnegative_int(case_book_gate.get("current_regression_case_count")),
        "target_regression_cases": _nonnegative_int(case_book_gate.get("target_regression_case_count")),
        "reviewed_external_evidence": _nonnegative_int(case_book_gate.get("reviewed_external_evidence_count")),
        "reviewed_evidence_target": _nonnegative_int(case_book_gate.get("reviewed_evidence_target_count")),
        "gaps": _string_list(case_book_gate.get("gaps")) + _string_list(replay_gate.get("gaps")),
    }


def _private_input_refs(*preflights: dict[str, Any]) -> list[str]:
    refs = []
    for preflight in preflights:
        ref = _string(preflight.get("private_input_ref")).strip()
        if ref:
            refs.append(ref)
    return sorted(set(refs))


def _next_actions(
    releasefoundry_gate: dict[str, Any],
    semantic_gate: dict[str, Any],
    case_book_gate: dict[str, Any],
    replay_gate: dict[str, Any],
) -> list[str]:
    actions = []
    if not _strict_true(releasefoundry_gate.get("safe_to_mark_c3_met")):
        actions.append("Collect, review, import, and merge all six ReleaseFoundry grading observations before marking C3 met.")
    if not _strict_true(semantic_gate.get("safe_to_mark_c4_met")):
        actions.append("Replace offline llm_judge references with audited live semantic judge summaries before marking C4 met.")
    if not _strict_true(case_book_gate.get("ready")) or not _strict_true(replay_gate.get("ready")):
        actions.append("Promote reviewed cross-judge disagreements until the case book and replay maturity gates both pass.")
    return actions


def _text_summary(preflight: dict[str, Any]) -> str:
    lines = [
        "A2 external evidence preflight",
        "network: off | private payloads: not read | writes files: no | API key value: never printed",
        "",
    ]
    for gate_id, gate in preflight["gate_summary"].items():
        status = "ready" if gate.get("safe_to_mark_met") or gate.get("case_book_ready") else "waiting"
        lines.append(f"{gate_id}: {status} ({gate.get('commercial_status', 'unknown')})")
        if gate.get("blocking_reason"):
            lines.append(f"  reason: {gate['blocking_reason']}")
        for gap in gate.get("gaps", []):
            lines.append(f"  gap: {gap}")
    lines.extend(["", "Next actions:"])
    lines.extend(f"- {action}" for action in preflight["next_actions"])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
