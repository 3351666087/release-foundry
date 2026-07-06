from __future__ import annotations

import json
from pathlib import Path

from packages.sdk.ashr_clone.api_client import summarize_quota_error
from packages.sdk.ashr_clone.evidence import build_private_evidence_index, build_private_evidence_index_from_dir, write_private_evidence_index


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
    assert index["records"][1]["quota"]["remaining"] == 0


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
