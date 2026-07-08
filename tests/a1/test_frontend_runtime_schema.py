from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROUND19_FIXTURE = ROOT / "tests" / "a1" / "fixtures" / "round19_frontend_contract_public.json"
ROUND20_FIXTURE = ROOT / "tests" / "a1" / "fixtures" / "round20_frontend_dashboard_dtos_public.json"
ROUND21_FIXTURE = ROOT / "tests" / "a1" / "fixtures" / "round21_frontend_runtime_schema_public.json"
FRONTEND_INDEX = ROOT / "docs" / "a1" / "frontend_mirror" / "frontend_mirror_index.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _all_domain_values(fixture: dict[str, Any], key: str) -> set[str]:
    values: set[str] = set()
    for domain in fixture["page_domains"].values():
        values.update(str(value) for value in domain[key])
    return values


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk_strings(child)]
    if isinstance(value, str):
        return [value]
    return []


def test_round21_runtime_schema_fixture_covers_frontend_page_domains():
    fixture = _load(ROUND21_FIXTURE)
    domains = fixture["page_domains"]

    assert fixture["schema_version"] == "ashr.a1.frontend_runtime_schema_public.v1"
    assert set(domains) == {"datasets", "folders", "team", "observability", "api_keys", "usage"}

    for domain in domains.values():
        assert domain["assets"]
        assert domain["api_functions"]
        assert domain["runtime_fields"]
        assert domain["copy_signals"]
        assert all(path.startswith("mirror/lab.ashr.io/assets/") for path in domain["assets"])


def test_round21_runtime_schema_matches_frontend_index_and_prior_fixtures():
    round19 = _load(ROUND19_FIXTURE)
    round20 = _load(ROUND20_FIXTURE)
    fixture = _load(ROUND21_FIXTURE)
    index = _load(FRONTEND_INDEX)

    observed_functions = _all_domain_values(fixture, "api_functions")
    assert observed_functions.issubset(set(index["api_functions"]))

    usage_fields = fixture["page_domains"]["usage"]["runtime_fields"]
    assert usage_fields == list(round19["usage"]["backend_key_to_label"].keys())
    assert set(usage_fields) == set(round20["dashboard_response_shapes"]["get_usage"]["usage"])

    api_key_fields = set(fixture["page_domains"]["api_keys"]["runtime_fields"])
    assert {"api_key_id", "created_at", "expires_seconds"}.issubset(api_key_fields)
    assert set(round20["dashboard_response_shapes"]["list_api_keys"]["api_keys"][0]).intersection(api_key_fields)

    dataset_fields = set(fixture["page_domains"]["datasets"]["runtime_fields"])
    assert {"request_id", "request_status", "dataset_source", "run_count"}.issubset(dataset_fields)

    observability_fields = set(fixture["page_domains"]["observability"]["runtime_fields"])
    assert {"agent_id", "duration_ms", "total_cost_usd", "status_code", "confidence_series", "observations"}.issubset(observability_fields)


def test_round21_runtime_schema_is_public_safe():
    fixture = _load(ROUND21_FIXTURE)
    serialized = json.dumps(fixture, sort_keys=True).lower()
    extracted_surface = {
        "page_domains": fixture["page_domains"],
        "runtime_contract_implications": fixture["runtime_contract_implications"],
        "next_mirror_gaps": fixture["next_mirror_gaps"],
    }
    all_strings = "\n".join(_walk_strings(extracted_surface)).lower()

    for forbidden in fixture["redaction_forbidden_fields"]:
        assert forbidden.lower() not in all_strings

    forbidden_fragments = [
        "bearer ",
        "sk-",
        "ashr_local_key_secret_",
        "set-cookie:",
        "private response",
        "raw private response:",
        "localstorage.",
        "sessionstorage.",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in serialized

    assert fixture["source"]["redaction"].startswith("Public-safe field names")
    assert any("live tenant payloads" in gap for gap in fixture["next_mirror_gaps"])