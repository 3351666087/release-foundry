from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.sdk.ashr_clone.calibrate import (
    CALIBRATION_MANIFEST_SCHEMA_VERSION,
    CalibrationArgs,
    CalibrationUsageError,
    parse_args,
    request_for_modality,
    run_calibration,
    selected_calibration_modalities,
)


class FakeCalibrationClient:
    base_url = "https://api.ashr.io/testing-platform-api"

    def __init__(self, *, quota_block: bool = False):
        self.calls: list[tuple[str, bool, str]] = []
        self.quota_block = quota_block

    def init(self, **kwargs):
        return self._record("init", {"status": "ok", "tenant": {"id": 1}, "user": {"id": 2}, "features": {"requests": True}}, **kwargs)

    def health_check(self, **kwargs):
        return self._record("keep_alive", {"status": "ok", "message": "alive"}, **kwargs)

    def list_agents(self, **kwargs):
        return self._record("list_agents", {"status": "ok", "agents": [{"id": 1}]}, **kwargs)

    def list_datasets(self, **kwargs):
        return self._record("list_datasets", {"status": "ok", "datasets": [{"id": 883}], "next_cursor": None}, **kwargs)

    def list_requests(self, **kwargs):
        return self._record("list_requests", {"status": "ok", "requests": [{"id": 581}], "next_cursor": None}, **kwargs)

    def create_request(self, **kwargs):
        if self.quota_block:
            return self._record(
                "create_request",
                {"status": "error", "message": "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining", "quota": {"resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0}},
                status="error",
                status_code=200,
                **kwargs,
            )
        return self._record("create_request", {"status": "ok", "request": {"id": 9001, "request_status": "pending"}}, **kwargs)

    def _record(self, function, response, *, dry_run=True, output_path=None, purpose="", status="ok", status_code=200, **_kwargs):
        self.calls.append((function, dry_run, str(output_path)))
        record = {
            "function": function,
            "dry_run": dry_run,
            "purpose": purpose,
            "started_at": "2026-07-05T00:00:00Z",
            "ended_at": "2026-07-05T00:00:00Z",
            "duration_ms": 1,
            "attempts": 0 if dry_run else 1,
            "status": "planned" if dry_run else status,
            "status_code": None if dry_run else status_code,
            "request": {"function": function, "params": {}, "estimated_calls": 1, "mutates": function == "create_request"},
            "response": {"plan": {"function": function}} if dry_run else response,
            "response_headers": {},
            "output_path": str(output_path) if output_path else None,
            "field_map_version": "a1-api-calibration-2026-07-04",
        }
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(json.dumps(record), encoding="utf-8")
        return record


def test_parse_args_defaults_to_safe_dry_run():
    args = parse_args([])

    assert args.execute is False
    assert args.include_mutating is False
    assert selected_calibration_modalities(args) == ("text", "image", "audio", "file", "video")


def test_parse_args_requires_small_batch_for_execute():
    with pytest.raises(SystemExit):
        parse_args(["--execute", "--max-retries", "0"])


def test_parse_args_requires_zero_retries_for_execute():
    with pytest.raises(SystemExit):
        parse_args(["--execute", "--small-batch"])


def test_parse_args_requires_paid_media_ack_for_mutating_media():
    with pytest.raises(SystemExit):
        parse_args(["--include-mutating", "--modality", "image"])


def test_request_for_modality_uses_object_accepted_inputs_for_all_modalities():
    for modality in ("text", "image", "audio", "file", "video"):
        request = request_for_modality(modality)
        assert sorted(request["accepted_inputs"].keys()) == ["audio", "file", "image", "text", "video"]
        assert request["accepted_inputs"]["text"]["enabled"] is True
        assert request["accepted_inputs"][modality]["enabled"] is True
        assert request["agent_input_schema_version"] == "ashr.clone.agent_input.v1"


def test_run_calibration_writes_dry_run_manifest_and_private_step_records(tmp_path: Path):
    output = tmp_path / "manifest.json"
    manifest = run_calibration(CalibrationArgs(output=str(output)), env={}, client=FakeCalibrationClient())

    assert manifest["schema_version"] == CALIBRATION_MANIFEST_SCHEMA_VERSION
    assert manifest["status"] == "planned"
    assert manifest["dry_run"] is True
    assert manifest["summary"]["total_steps"] == 5
    assert manifest["summary"]["mutating_steps"] == 0
    assert output.exists()
    for step in manifest["steps"]:
        assert Path(step["private_record_path"]).exists()


def test_run_calibration_small_batch_with_text_mutation(tmp_path: Path):
    output = tmp_path / "real.json"
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output))
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient())

    assert manifest["status"] == "ok"
    assert manifest["summary"]["read_steps"] == 5
    assert manifest["summary"]["mutating_steps"] == 1
    assert manifest["summary"]["modalities"] == ["text"]
    assert "tp_syntheticsecret" not in json.dumps(manifest)


def test_run_calibration_captures_quota_block_without_raw_secret(tmp_path: Path):
    output = tmp_path / "quota.json"
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output))
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient(quota_block=True))

    assert manifest["status"] == "partial"
    assert manifest["summary"]["quota_block_count"] == 1
    assert manifest["errors"][0]["quota"]["remaining"] == 0
    assert "tp_syntheticsecret" not in json.dumps(manifest)