from __future__ import annotations

import json
from pathlib import Path

from packages.sdk.releasefoundry.capability_matrix import load_public_json
from packages.sdk.releasefoundry.commercial import build_commercial_control_plane_kit, validate_commercial_control_plane_kit

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "docs" / "a1" / "commercial" / "control_plane_kit.json"
SCHEMA = ROOT / "docs" / "a1" / "schemas" / "commercial_control_plane.schema.json"


def test_commercial_control_plane_kit_is_enterprise_saas_artifact():
    kit = load_public_json(KIT)
    schema = load_public_json(SCHEMA)

    assert kit["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert kit["product_posture"] == "enterprise_saas_control_plane_evidence_kit"
    assert {
        "usage_billing_governance",
        "api_key_lifecycle_governance",
        "observability_and_cost_analytics",
        "release_gate_and_audit_evidence",
    } <= set(kit["saas_control_plane_pillars"])
    assert kit["readiness_badge"]["enterprise_saas_surface"] is True
    assert kit["readiness_badge"]["read_only_current"] is True
    assert kit["readiness_badge"]["paid_mutation_executed_this_round"] is False
    assert not validate_commercial_control_plane_kit(kit)


def test_commercial_control_plane_kit_covers_usage_api_keys_observability_without_sensitive_values():
    kit = load_public_json(KIT)
    labels = {item["label"] for item in kit["usage_billing_snapshot"]["usage_dimensions"]}
    key_text = json.dumps(kit["api_key_inventory"], sort_keys=True)
    full_text = json.dumps(kit, sort_keys=True)

    assert {"Images", "Audio", "Files", "Videos", "Voice minutes"} <= labels
    assert kit["usage_billing_snapshot"]["real_billing_called"] is False
    assert kit["usage_billing_snapshot"]["checkout_or_portal_called"] is False
    assert kit["api_key_inventory"]["raw_sensitive_values_included"] is False
    assert all(item["sensitive_value_present"] is False for item in kit["api_key_inventory"]["keys"])
    assert "releasefoundry_local_key" not in key_text
    assert "secret_hash_sha256" not in key_text
    assert "private_refs" not in full_text
    assert "RELEASEFOUNDRY_API_KEY" not in full_text
    assert "Bearer " not in full_text
    assert kit["observability_summary"]["metrics"]["frontend_mirrored_capabilities"] >= 100


def test_commercial_control_plane_builder_recreates_artifact():
    cap = load_public_json(ROOT / "docs" / "a1" / "commercial" / "capability_matrix.json")
    fm = load_public_json(ROOT / "docs" / "a1" / "frontend_mirror" / "frontend_mirror_index.json")
    ev = load_public_json(ROOT / "docs" / "a1" / "api_calibration" / "real_api_evidence_index.json")
    kit = build_commercial_control_plane_kit(capability_matrix=cap, frontend_mirror_index=fm, evidence_index=ev)

    assert kit == load_public_json(KIT)
