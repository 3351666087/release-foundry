from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT
    / "docs"
    / "a1"
    / "evidence"
    / "oauth_adversarial_multi_instance_template.json"
)


def _template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def test_oauth_reliability_template_covers_required_adversarial_controls() -> None:
    template = _template()
    controls = {item["control_id"]: item for item in template["controls"]}

    assert set(controls) == {
        "forged_host_rejected",
        "state_replay_denied",
        "google_oidc_claim_validation",
        "provider_outage_timeout",
        "restart_replay_persistence",
        "multi_instance_atomic_consume",
        "reconnect_revocation",
        "public_response_no_token_refs",
    }
    assert controls["restart_replay_persistence"]["status"] == "blocked"
    assert controls["multi_instance_atomic_consume"]["status"] == "blocked"
    assert controls["reconnect_revocation"]["status"] == "blocked"
    assert all(
        control["status"] != "verified"
        for control in (
            controls["restart_replay_persistence"],
            controls["multi_instance_atomic_consume"],
            controls["reconnect_revocation"],
        )
    )


def test_oauth_reliability_template_is_public_safe_and_has_no_auth_material() -> None:
    template = _template()
    serialized = json.dumps(template, sort_keys=True).lower()
    forbidden_fields = set(template["forbidden_runtime_evidence_fields"])

    assert template["public_safe"] is True
    assert template["secret_value_present"] is False
    assert template["raw_authorization_material_present"] is False
    assert {
        "authorization_code",
        "state",
        "nonce",
        "pkce_verifier",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "token_ref",
    }.issubset(forbidden_fields)
    assert "ghp_" not in serialized
    assert "github_oauth_ref_" not in serialized
    assert "ya29." not in serialized


def test_every_verified_control_points_to_executable_a1_tests() -> None:
    template = _template()

    for control in template["controls"]:
        if not control["status"].startswith("verified"):
            continue
        selectors = control.get("test_selector", "").split()
        assert selectors, control["control_id"]
        for selector in selectors:
            path = ROOT / selector
            assert path.is_file(), (control["control_id"], selector)
            assert path.suffix == ".py", (control["control_id"], selector)


def test_blocked_controls_name_concrete_unmet_evidence() -> None:
    template = _template()

    for control in template["controls"]:
        if control["status"] != "blocked":
            continue
        assert len(control["blocked_by"]) >= 24
        assert len(control["required_evidence"]) >= 3
        assert all(item.strip() for item in control["required_evidence"])
