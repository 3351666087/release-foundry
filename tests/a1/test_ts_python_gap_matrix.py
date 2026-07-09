from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "tests" / "a1" / "docs" / "a1" / "ts_python_gap_matrix.json"


def _matrix_by_area(matrix: dict) -> dict[str, dict]:
    return {entry["area"]: entry for entry in matrix["gap_matrix"]}


def test_ts_python_gap_matrix_is_public_safe_and_actionable():
    matrix = json.loads(ARTIFACT.read_text(encoding="utf-8-sig"))

    assert matrix["schema_version"] == "ashr.clone.a1_ts_python_gap_matrix.v1"
    assert matrix["public_safe"] is True
    assert matrix["secret_policy"] == {
        "private_evidence_read": False,
        "tokens_included": False,
        "raw_private_payloads_included": False,
        "input_sources": [
            "packages/sdk/ashr_clone public module source",
            "packages/ts/ashr-clone/src public module source",
            "tests/a1 and tests/integration public test names",
        ],
    }

    text = ARTIFACT.read_text(encoding="utf-8-sig")
    for forbidden in ("private_refs", "sk-", "Bearer ", "ashr_live_", "tp_"):
        assert forbidden not in text

    by_area = _matrix_by_area(matrix)
    required_areas = {
        "exported Python functions/classes/types vs TS exports",
        "API calibration features",
        "SaaS control-plane features",
        "CLI commands",
        "adapter/runner/trace features",
        "media text/audio/file/image/video parity",
    }
    assert set(by_area) == required_areas

    assert by_area["API calibration features"]["status"] == "python_leads"
    assert by_area["SaaS control-plane features"]["status"] == "partial"
    assert by_area["CLI commands"]["status"] == "partial"
    assert by_area["media text/audio/file/image/video parity"]["status"] == "parity_with_packaging_gaps"

    cli = by_area["CLI commands"]
    assert "bootstrap" in cli["python_commands"]["ashr_clone.saas_cli"]
    assert "release-gate" in cli["typescript_commands"]["saas"]
    assert any("TS SaaS CLI does not expose" in gap for gap in cli["gaps"])

    exports = by_area["exported Python functions/classes/types vs TS exports"]
    assert any("CloudApiService" in gap for gap in exports["typescript_leads"])
    assert any("capability_matrix" in gap for gap in exports["python_leads"])

    media = by_area["media text/audio/file/image/video parity"]
    joined_media = json.dumps(media, sort_keys=True)
    for modality in ("text", "image", "audio", "file", "video"):
        assert modality in joined_media

    for entry in matrix["gap_matrix"]:
        assert entry["status"] in {"parity", "partial", "python_leads", "typescript_leads", "typescript_leads_runtime_exports", "parity_with_packaging_gaps"}
        assert entry["evidence"]
        for path in entry["evidence"]:
            assert not Path(path).is_absolute()
            assert "private" not in path.lower()
            assert "secret" not in path.lower()
