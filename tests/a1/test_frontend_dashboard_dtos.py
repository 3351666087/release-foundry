from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROUND19_FIXTURE = ROOT / "tests" / "a1" / "fixtures" / "round19_frontend_contract_public.json"
ROUND20_FIXTURE = ROOT / "tests" / "a1" / "fixtures" / "round20_frontend_dashboard_dtos_public.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def test_round20_dashboard_dtos_use_round19_frontend_mirror_fields():
    round19 = _load(ROUND19_FIXTURE)
    fixture = _load(ROUND20_FIXTURE)
    shapes = fixture["dashboard_response_shapes"]

    assert fixture["schema_version"] == "releasefoundry.a1.frontend_dashboard_dtos_public.v1"
    assert set(shapes) == {"get_usage", "list_api_keys", "billing_get_status"}
    assert {shape["function"] for shape in shapes.values()} == {"get_usage", "list_api_keys", "billing_get_status"}

    expected_usage_labels = round19["usage"]["backend_key_to_label"]
    usage = shapes["get_usage"]["usage"]
    assert set(usage) == set(expected_usage_labels)
    for key, label in expected_usage_labels.items():
        assert usage[key]["label"] == label

    api_key = shapes["list_api_keys"]["api_keys"][0]
    for frontend_field in ["api_key_id", "created_at", "expires_seconds"]:
        assert frontend_field in api_key
        assert frontend_field in round19["frontend_fields"]

    assert shapes["list_api_keys"]["empty_state"] == round19["empty_states"]["api_keys"]
    assert shapes["get_usage"]["tabs"] == round19["usage"]["tabs"]


def test_round20_quota_cards_cover_thresholds_and_cap_badges():
    fixture = _load(ROUND20_FIXTURE)
    cards = {card["metric_key"]: card for card in fixture["dashboard_response_shapes"]["get_usage"]["quota_cards"]}

    assert cards["images"]["percent_used"] == 74
    assert cards["images"]["severity"] == "normal"
    assert cards["simulations"]["percent_used"] == 76
    assert cards["simulations"]["severity"] == "warning"
    assert cards["audios"]["percent_used"] == 91
    assert cards["audios"]["severity"] == "error"
    assert cards["audios"]["badge"] == "Over included usage"
    assert cards["files"]["badge"] == "Limit reached"
    assert cards["graded_scenarios"]["badge"] == "Overage billing"


def test_round20_dashboard_dtos_are_public_safe():
    fixture = _load(ROUND20_FIXTURE)
    observed_keys = {key.lower() for key in _walk_keys(fixture["dashboard_response_shapes"])}

    for forbidden in fixture["redaction_forbidden_fields"]:
        assert forbidden.lower() not in observed_keys

    serialized = json.dumps(fixture, sort_keys=True).lower()
    forbidden_fragments = [
        "bearer ",
        "sk-",
        "releasefoundry_local_key_secret_",
        "set-cookie",
        "private response",
        "raw private response:",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in serialized

    api_key = fixture["dashboard_response_shapes"]["list_api_keys"]["api_keys"][0]
    assert api_key["secret_value_present"] is False
    assert api_key["one_time_secret_displayed"] is False
