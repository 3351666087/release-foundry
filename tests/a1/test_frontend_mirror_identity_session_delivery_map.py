from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIELD_MAP = ROOT / "docs" / "a1" / "evidence" / "frontend_mirror_identity_session_delivery_map_20260711.json"
FRONTEND_INDEX = ROOT / "docs" / "a1" / "frontend_mirror" / "frontend_mirror_index.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk_strings(child)]
    return [value] if isinstance(value, str) else []


def test_frontend_mirror_identity_session_delivery_map_has_pinned_snapshot_provenance() -> None:
    field_map = _load(FIELD_MAP)
    index = _load(FRONTEND_INDEX)
    provenance = field_map["provenance"]

    assert field_map["schema_version"] == "ashr.a1.frontend_mirror_identity_session_delivery_map.v1"
    assert provenance["source_kind"] == "offline_frontend_mirror_snapshot"
    assert provenance["source_sha256"] == index["source_sha256"]
    assert provenance["archive_entry_count"] == index["scanned_entry_count"] == 589
    assert provenance["live_browser_verified"] is False
    assert provenance["live_ui_claimed"] is False
    assert provenance["raw_source_committed"] is False

    roles = {asset["role"] for asset in field_map["assets"]}
    assert {
        "hosted_auth_and_api_dispatch",
        "api_key_page",
        "observability_sessions",
        "request_lifecycle",
        "python_authentication_documentation",
        "typescript_authentication_documentation",
    } == roles
    for asset in field_map["assets"]:
        assert asset["path"].startswith("mirror/")
        assert re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
        assert asset["size_bytes"] > 0


def test_frontend_mirror_map_separates_identity_login_and_domain_sessions() -> None:
    mapped = _load(FIELD_MAP)["field_and_state_map"]

    assert mapped["verified_identity"]["evidence_level"] == "not_observed"
    assert mapped["identity_verification_delivery"]["evidence_level"] == "not_observed"
    assert mapped["verified_identity"]["state_machine"]["transition_graph_verified"] is False
    assert mapped["identity_verification_delivery"]["state_machine"]["transition_graph_verified"] is False

    hosted = mapped["hosted_auth_session"]
    assert {"access_token", "auth_provider", "expires_in", "refresh_token"} == set(hosted["observed_fields"])
    assert {"sign in", "sign out"} == set(hosted["observed_actions"])
    assert hosted["state_machine"]["verified_transitions"] == []

    domain = mapped["voice_and_observability_session"]
    assert {"session_id", "duration_ms", "status_code", "status_message", "observations"} == set(
        domain["observed_fields"]
    )
    assert "account-login session" in domain["interpretation"]
    assert domain["state_machine"]["transition_graph_verified"] is False


def test_frontend_mirror_map_records_api_actions_without_runtime_claims() -> None:
    mapped = _load(FIELD_MAP)["field_and_state_map"]
    api_keys = mapped["api_key_lifecycle"]
    dispatch = mapped["api_dispatch"]
    requests = mapped["request_lifecycle"]

    assert {"create_api_key", "list_api_keys", "revoke_api_key"} == set(api_keys["observed_api_functions"])
    assert {"api_key_id", "expires_at", "expires_in", "key_prefix"} == set(api_keys["observed_fields"])
    assert api_keys["state_machine"]["verified_transitions"] == []
    assert api_keys["state_machine"]["transition_graph_verified"] is False

    assert {"auth_provider", "function"} == set(dispatch["observed_request_fields"])
    assert {"status", "message", "error"} == set(dispatch["observed_result_fields"])
    assert dispatch["endpoint_behavior_verified"] is False

    assert {"Queued", "Processing", "Completed", "Failed", "pending"} == set(
        requests["state_machine"]["observed_state_labels"]
    )
    assert requests["state_machine"]["verified_transitions"] == []
    assert requests["state_machine"]["transition_graph_verified"] is False


def test_frontend_mirror_map_is_public_safe_and_explicit_about_unknowns() -> None:
    field_map = _load(FIELD_MAP)
    safety = field_map["public_safety"]
    serialized = json.dumps(field_map, sort_keys=True).lower()
    strings = _walk_strings(field_map)

    assert safety
    assert all(value is False for value in safety.values())
    assert len(field_map["unknowns"]) >= 6
    assert any("Live UI state was unavailable" in item for item in field_map["unknowns"])
    assert any("No endpoint was called" in item for item in field_map["unknowns"])

    forbidden_fragments = [
        "authorization:",
        "bearer ",
        "set-cookie:",
        "callback?",
        "code=",
        "state=",
        "source_excerpt",
        "raw_source_text",
        "raw_payload_value",
    ]
    assert not any(fragment in serialized for fragment in forbidden_fragments)
    assert not any("@" in value for value in strings)
    assert not any("?" in value and "=" in value for value in strings)
