from __future__ import annotations

import json
from pathlib import Path

from packages.sdk.ashr_clone.api_client import summarize_quota_error
from packages.sdk.ashr_clone.evidence import (
    build_private_evidence_index,
    build_private_evidence_index_from_dir,
    build_response_field_map,
    merge_evidence_indices,
    render_response_field_map_markdown,
    validate_public_evidence_index,
    write_private_evidence_index,
    write_response_field_map_markdown,
)


def test_summarize_quota_error_handles_real_hosted_shape():
    record = {
        "function": "create_request",
        "status": "error",
        "error": {
            "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
            "error_kind": "api",
            "response": {
                "status": "error",
                "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
                "quota": {"resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0},
            },
        },
    }

    summary = summarize_quota_error(record)

    assert summary == {
        "blocked": True,
        "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
        "quota_keys": ["limit", "remaining", "requested", "resource", "used"],
        "resource": "requests",
        "limit": 5,
        "used": 5,
        "requested": 1,
        "remaining": 0,
    }


def test_evidence_index_extracts_safe_shapes_without_raw_payload(tmp_path: Path):
    ok_record = tmp_path / "ok.json"
    ok_record.write_text(
        json.dumps(
            {
                "function": "list_datasets",
                "dry_run": False,
                "status": "ok",
                "status_code": 200,
                "attempts": 1,
                "request": {"function": "list_datasets", "params": {"tenant_id": 36}},
                "response": {"status": "ok", "datasets": [{"id": 1, "name": "Sensitive raw dataset name"}], "next_cursor": 1},
                "response_headers": {},
            }
        ),
        encoding="utf-8",
    )
    quota_record = tmp_path / "quota.json"
    quota_record.write_text(
        json.dumps(
            {
                "function": "create_request",
                "dry_run": False,
                "status": "error",
                "status_code": 200,
                "attempts": 1,
                "request": {"params": {"request": {"prompt": "raw prompt must not appear"}}},
                "response_headers": {},
                "error": {
                    "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
                    "error_kind": "api",
                    "response": {
                        "status": "error",
                        "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
                        "quota": {"resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    index = build_private_evidence_index([ok_record, quota_record], label="test-index")

    assert index["schema_version"] == "ashr.clone.evidence_index.v1"
    assert index["total_records"] == 2
    assert index["status_counts"] == {"error": 1, "ok": 1}
    assert index["function_counts"] == {"create_request": 1, "list_datasets": 1}
    assert index["quota_block_count"] == 1
    assert index["error_kind_counts"] == {"api": 1}
    assert index["records"][0]["response_keys"]
    assert "Sensitive raw dataset name" not in json.dumps(index)
    assert "raw prompt must not appear" not in json.dumps(index)
    assert index["records"][0]["path"].endswith("ok.json")
    quota = index["records"][1]["quota"]
    assert quota["resource"] == "requests"
    assert quota["limit_present"] is True
    assert quota["used_present"] is True
    assert quota["requested_present"] is True
    assert quota["remaining_present"] is True
    index_text = json.dumps(index)
    assert ("5/5 " + "used") not in index_text
    assert ('"remaining": ' + "0") not in index_text
    assert validate_public_evidence_index(index) == []
    field_map = build_response_field_map(index)
    assert field_map["schema_version"] == "ashr.clone.response_field_map.v1"
    assert field_map["functions"]["create_request"]["quota_block_count"] == 1
    assert field_map["functions"]["create_request"]["statuses"] == {"error": 1}
    assert field_map["functions"]["list_datasets"]["response_keys"] == ["datasets", "next_cursor", "status"]


def test_public_evidence_linter_catches_exact_quota_values():
    quota = {"blocked": True, "quota_keys": ["used", "remaining"]}
    quota["used"] = int("5")
    quota["remaining"] = int("0")
    index = {
        "records": [
            {
                "function": "create_request",
                "quota": quota,
            }
        ]
    }

    issues = validate_public_evidence_index(index)

    assert {issue["kind"] for issue in issues} >= {"exact_quota_detail", "quota_value_not_public_safe"}


def test_public_evidence_linter_scans_raw_secret_like_values_before_redaction():
    index = {
        "records": [
            {"path": "public.json", "response_keys": ["status"], "note": "tp_" + "syntheticsecret"},
            {"path": "public2.json", "message": "Bearer " + "abc.def"},
            {"path": "public3.json", "message": "sk-" + "testtesttest"},
            {"path": "public4.json", "message": "ashr_live_" + "synthetic"},
        ]
    }

    issues = validate_public_evidence_index(index)

    assert [issue["kind"] for issue in issues].count("secret_like_text") == 4


def test_evidence_index_from_dir_and_write_roundtrip(tmp_path: Path):
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"function": "init", "status": "ok", "response": {"status": "ok", "user": {"email": "owner@example.com"}}}), encoding="utf-8")
    output = tmp_path / "index.json"

    index = build_private_evidence_index_from_dir(tmp_path)
    write_private_evidence_index(output, index)
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert loaded["total_records"] == 1
    assert "owner@example.com" not in json.dumps(loaded)
    assert loaded["records"][0]["response_keys"] == ["status", "user"]


def test_public_evidence_index_matches_schema():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "docs" / "a1" / "schemas" / "evidence_index.schema.json").read_text(encoding="utf-8"))
    index = json.loads((root / "docs" / "a1" / "api_calibration" / "real_api_evidence_index.json").read_text(encoding="utf-8"))

    for field in schema["required"]:
        assert field in index
    assert index["total_records"] == len(index["records"])
    assert not any(":" in record["path"] or "\\" in record["path"] for record in index["records"])
    required_record_fields = set(schema["properties"]["records"]["items"]["required"])
    for record in index["records"]:
        assert required_record_fields.issubset(record)
        assert isinstance(record["request_keys"], list)
        assert isinstance(record["response_keys"], list)
        assert isinstance(record["top_counts"], dict)


def test_merge_evidence_indices_preserves_existing_public_records(tmp_path: Path):
    missing_private_record = {
        "path": "docs/evidence/private_refs/missing_raw_record.json",
        "function": "get_request",
        "dry_run": False,
        "status": "ok",
        "status_code": 200,
        "attempts": 1,
        "request_keys": ["function"],
        "response_keys": ["request", "status"],
        "response_status": "ok",
        "response_summary_keys": [],
        "error_keys": [],
        "error_kind": None,
        "top_counts": {},
    }
    existing = {
        "schema_version": "ashr.clone.evidence_index.v1",
        "label": "old",
        "records": [missing_private_record],
    }
    fresh_record_path = tmp_path / "fresh.json"
    fresh_record_path.write_text(
        json.dumps(
            {
                "function": "create_request",
                "dry_run": False,
                "status": "error",
                "status_code": 200,
                "attempts": 1,
                "request": {"params": {"request_name": "Synthetic calibration"}},
                "error": {
                    "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
                    "error_kind": "api",
                    "response": {
                        "status": "error",
                        "quota": {"resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    merged = merge_evidence_indices(existing, build_private_evidence_index([fresh_record_path], label="fresh"), label="merged")

    assert merged["label"] == "merged"
    assert merged["total_records"] == 2
    assert merged["status_counts"] == {"error": 1, "ok": 1}
    assert merged["function_counts"] == {"create_request": 1, "get_request": 1}
    assert merged["quota_block_count"] == 1
    assert any(record["path"] == missing_private_record["path"] for record in merged["records"])


def test_public_response_field_map_artifact_is_generated():
    root = Path(__file__).resolve().parents[2]
    field_map = json.loads((root / "docs" / "a1" / "api_calibration" / "real_api_response_field_map.json").read_text(encoding="utf-8"))

    assert field_map["schema_version"] == "ashr.clone.response_field_map.v1"
    assert field_map["source_total_records"] >= 200
    assert "create_request" in field_map["functions"]
    assert "list_requests" in field_map["functions"]
    assert "requests" in field_map["functions"]["list_requests"]["top_count_keys"]


def test_response_field_map_markdown_report_is_public_safe(tmp_path: Path):
    field_map = {
        "schema_version": "ashr.clone.response_field_map.v1",
        "source_label": "test-public-report",
        "source_total_records": 200,
        "field_map_version": "a1-api-calibration-2026-07-04",
        "functions": {
            "create_request": {
                "records": 21,
                "statuses": {"error": 10, "planned": 11},
                "response_keys": ["plan", "status"],
                "error_keys": ["error_kind", "message"],
                "top_count_keys": [],
                "quota_block_count": 10,
            }
        },
    }

    markdown = render_response_field_map_markdown(field_map)
    output = write_response_field_map_markdown(tmp_path / "field-map.md", field_map)

    assert output.exists()
    assert "# Ashr Real API Response Field Map" in markdown
    assert "`create_request`" in markdown
    assert "`error`: 10" in markdown
    assert "200" in markdown
    assert "5/5 used" not in markdown
    assert '"remaining": 0' not in markdown
    assert output.read_text(encoding="utf-8") == markdown
