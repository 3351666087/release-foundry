from __future__ import annotations

import json
from pathlib import Path

from tests.a1.ts_python_parity_matrix import ARTIFACT, MEDIA_MODALITIES, REQUIRED_HOSTED_ROUTE_LITERALS, generate_matrix


def _matrix_by_area(matrix: dict) -> dict[str, dict]:
    return {entry["area"]: entry for entry in matrix["gap_matrix"]}


def test_ts_python_gap_matrix_is_generated_public_safe_and_current():
    matrix = json.loads(ARTIFACT.read_text(encoding="utf-8-sig"))
    assert matrix == generate_matrix()

    assert matrix["schema_version"] == "ashr.clone.a1_ts_python_gap_matrix.v2"
    assert matrix["public_safe"] is True
    assert matrix["secret_policy"] == {
        "private_evidence_read": False,
        "tokens_included": False,
        "raw_private_payloads_included": False,
        "input_sources": [
            "packages/sdk/ashr_clone public module source",
            "packages/ts/ashr-clone public package metadata and src source",
            "tests/a1 generated public parity generator",
        ],
    }

    text = ARTIFACT.read_text(encoding="utf-8-sig")
    for forbidden in ("private_refs", "sk-", "Bearer ", "ashr_live_", "tp_"):
        assert forbidden not in text

    by_area = _matrix_by_area(matrix)
    assert set(by_area) == {
        "exported Python functions/classes/types vs TS exports",
        "CLI commands",
        "SaaS route literals",
        "media text/audio/file/image/video parity",
        "official API calibration SDK import surface",
    }
    assert by_area["CLI commands"]["status"] in {"parity", "typescript_leads"}
    assert by_area["media text/audio/file/image/video parity"]["status"] == "parity"
    assert by_area["official API calibration SDK import surface"]["status"] == "parity"

    symbols = matrix["generated_contract"]["symbols"]
    assert "SaaSIngestionClient" in symbols["shared_export_names"]
    assert "CloudApiService" in symbols["typescript_only_export_names"]
    assert "capability_matrix" not in symbols["typescript_effective_export_names"]

    cli = matrix["generated_contract"]["cli"]
    assert "bootstrap" in cli["python_commands"]["ashr_clone.saas_cli"]
    assert "release-gate" in cli["typescript_commands"]["saas"]
    assert cli["python_only_saas_command_names"] == []
    assert "job-lease" in cli["typescript_only_saas_command_names"]

    routes = matrix["generated_contract"]["routes"]
    assert "/v1/bootstrap" in routes["shared_route_literals"]
    assert routes["python_saas_route_literals"]
    assert routes["typescript_saas_route_literals"]
    assert routes["required_hosted_route_literals"] == REQUIRED_HOSTED_ROUTE_LITERALS
    assert routes["missing_required_python_hosted_routes"] == []
    assert routes["missing_required_typescript_hosted_routes"] == []

    media = matrix["generated_contract"]["media"]
    assert media["required_modalities"] == MEDIA_MODALITIES
    assert media["python"]["agent_input_part_types"] == MEDIA_MODALITIES
    assert media["typescript"]["agent_input_part_types"] == MEDIA_MODALITIES
    assert media["typescript"]["safe_media_envelope_exported"] is True

    calibration = matrix["generated_contract"]["calibration"]
    assert calibration["typescript"]["barrel_module_exported"] is True
    assert calibration["typescript"]["missing_required_exports"] == []
    assert calibration["typescript"]["sdk_import_surface"] == "public"

    for entry in matrix["gap_matrix"]:
        assert entry["status"] in {"parity", "partial", "python_leads", "typescript_leads"}
        assert entry["evidence"]
        for path in entry["evidence"]:
            assert not Path(path).is_absolute()
            assert "private" not in path.lower()
            assert "secret" not in path.lower()
