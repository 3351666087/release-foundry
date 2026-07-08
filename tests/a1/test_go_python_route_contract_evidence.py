from __future__ import annotations

import json
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is optional in the light test env
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "docs" / "a1" / "go_python_route_contract_evidence.json"
SCHEMA = ROOT / "docs" / "a1" / "schemas" / "go_python_route_contract_evidence.schema.json"


def _load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_go_python_route_contract_artifact_matches_schema_shape():
    artifact = _load_artifact()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    for field in schema["required"]:
        assert field in artifact
    assert artifact["schema_version"] == "ashr.clone.go_python_route_contract_evidence.v1"
    assert artifact["public_safe"] is True
    assert artifact["source_policy"]["private_evidence_read"] is False
    assert artifact["source_policy"]["raw_payloads_included"] is False
    assert artifact["source_policy"]["tokens_included"] is False

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(artifact)


def test_go_python_route_contract_references_public_existing_paths():
    artifact = _load_artifact()

    paths: set[str] = set()
    for owner in artifact["ownership_summary"]:
        paths.update(owner["primary_paths"])
    for route in artifact["route_contracts"]:
        paths.update(route["producer_paths"])
    for consumer in artifact["consumer_contracts"]:
        paths.update(consumer["stable_inputs"])
    for evidence in artifact["evidence_artifacts"]:
        paths.add(evidence["path"])

    for path in sorted(paths):
        assert not Path(path).is_absolute(), path
        assert "private_refs" not in path, path
        assert not path.startswith(("recon/", "tools/", ".secrets/")), path
        assert (ROOT / path).exists(), path


def test_go_python_route_contract_does_not_leak_private_markers():
    text = ARTIFACT.read_text(encoding="utf-8")

    assert "docs/evidence/private_refs/**" in text
    for marker in ("tp_", "sk-", "Bearer ", "ashr_live_", "raw prompt", "owner@example.com"):
        assert marker not in text


def test_go_python_route_contract_symbols_match_current_source():
    artifact = _load_artifact()
    source_cache: dict[str, str] = {}

    for route in artifact["route_contracts"]:
        source_text = "\n".join(
            source_cache.setdefault(path, (ROOT / path).read_text(encoding="utf-8")) for path in route["producer_paths"]
        )
        for symbol in route["contract_symbols"]:
            if "." in symbol:
                symbol_name = symbol.rsplit(".", 1)[1]
            else:
                symbol_name = symbol
            assert symbol_name in source_text, f"{route['id']} references missing symbol {symbol}"


def test_go_python_route_contract_declares_a2_a3_handoffs():
    artifact = _load_artifact()

    consumers = {entry["consumer"]: entry for entry in artifact["consumer_contracts"]}
    assert set(consumers) == {"a2", "a3"}
    assert any("python.a2_judge_release_contracts" in item for item in consumers["a2"]["can_consume"])
    assert any("Go route family names" in item for item in consumers["a3"]["can_consume"])
    for consumer in consumers.values():
        joined_forbidden = "\n".join(consumer["must_not_consume"])
        assert "private" in joined_forbidden
