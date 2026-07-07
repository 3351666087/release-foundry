from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from packages.sdk.ashr_clone.calibrate import (
    CALIBRATION_MANIFEST_SCHEMA_VERSION,
    DEFAULT_QUOTA_GATE_TTL_SECONDS,
    PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION,
    CalibrationArgs,
    CalibrationUsageError,
    calibration_request_fingerprint,
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


def gate_created_at_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_plan_batch_gate(
    tmp_path: Path,
    *,
    decision: str = "go",
    target_operation: str = "create-request",
    created_at: str | None = None,
    modalities: list[str] | None = None,
    request_fingerprint=None,
) -> Path:
    gate = {
        "decision": decision,
        "source": "quota-record",
        "quota_or_reset_evidence_present": True,
        "reset": {"known": False, "wait_hint_present": False, "header_keys": ["x-ratelimit-remaining"]},
        "can_enter_small_batch": decision == "go",
        "can_enter_batch": decision == "go",
    }
    if decision != "go":
        gate["quota"] = {"blocked": True, "resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0}
    plan = {
        "schema_version": PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION,
        "target_operation": target_operation,
        "created_at": created_at or gate_created_at_now(),
        "quota_stop_go": gate,
    }
    if modalities is not None:
        plan["modalities"] = modalities
    if request_fingerprint is not None:
        plan["request_fingerprint"] = request_fingerprint
    record = {
        "schema_version": PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION,
        "function": "plan_batch",
        "dry_run": True,
        "status": "blocked" if decision == "stop" else "planned",
        "response": {"plan": plan},
        "field_map_version": "a1-api-calibration-2026-07-04",
    }
    path = tmp_path / f"quota_gate_{decision}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_parse_args_defaults_to_safe_dry_run():
    args = parse_args([])

    assert args.execute is False
    assert args.include_mutating is False
    assert args.quota_gate_ttl_seconds == DEFAULT_QUOTA_GATE_TTL_SECONDS
    assert selected_calibration_modalities(args) == ("text", "image", "audio", "file", "video")


def test_parse_args_accepts_zero_quota_gate_ttl_and_rejects_negative():
    args = parse_args(["--quota-gate-ttl-seconds", "0"])

    assert args.quota_gate_ttl_seconds == 0

    with pytest.raises(SystemExit):
        parse_args(["--quota-gate-ttl-seconds", "-1"])


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
        agent = request["agent"]
        assert sorted(agent["accepted_inputs"].keys()) == [
            "audio",
            "conversation",
            "file",
            "image",
            "text",
            "video",
        ]
        assert agent["accepted_inputs"]["text"]["enabled"] is True
        assert agent["accepted_inputs"][modality]["enabled"] is True
        assert agent["output_format"] == {"type": "text"}
        assert request["generation_options"]["generate_images"] is (modality == "image")
        assert request["generation_options"]["generate_audio"] is (modality == "audio")
        assert request["generation_options"]["generate_files"] is (modality == "file")
        assert request["generation_options"]["generate_videos"] is (modality == "video")
        assert request["generation_options"]["generate_simulations"] is False
        assert "accepted_inputs" not in request
        assert "agent_input_parts" not in request


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


def test_run_calibration_execute_read_only_does_not_require_quota_gate(tmp_path: Path):
    output = tmp_path / "read_only_real.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, max_retries=0, output=str(output))
    manifest = run_calibration(args, env={}, client=client)

    assert manifest["status"] == "ok"
    assert manifest["summary"]["read_steps"] == 5
    assert manifest["summary"]["mutating_steps"] == 0
    assert all(call[0] != "create_request" for call in client.calls)
    assert manifest["guardrails"]["quota_gate"] is None


def test_run_calibration_mutating_execute_requires_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "missing_gate.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output))

    with pytest.raises(CalibrationUsageError, match="quota-gate-record"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_read_only_success_record_as_quota_gate(tmp_path: Path):
    output = tmp_path / "wrong_gate.json"
    read_only_record = tmp_path / "list_requests_record.json"
    read_only_record.write_text(
        json.dumps(
            {
                "function": "list_requests",
                "dry_run": False,
                "status": "ok",
                "response": {"status": "ok", "requests": []},
                "field_map_version": "a1-api-calibration-2026-07-04",
            }
        ),
        encoding="utf-8",
    )
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(read_only_record))

    with pytest.raises(CalibrationUsageError, match="plan-batch quota gate record"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_stop_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "stop_gate.json"
    gate = write_plan_batch_gate(tmp_path, decision="stop")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="quota gate decision=stop"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_go_quota_gate_without_evidence(tmp_path: Path):
    output = tmp_path / "go_without_evidence.json"
    gate = write_plan_batch_gate(tmp_path)
    payload = json.loads(gate.read_text(encoding="utf-8"))
    quota_gate = payload["response"]["plan"]["quota_stop_go"]
    quota_gate["source"] = "not-provided"
    quota_gate.pop("quota_or_reset_evidence_present", None)
    quota_gate.pop("reset", None)
    gate.write_text(json.dumps(payload), encoding="utf-8")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="requires reviewed quota/reset evidence"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_stale_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "stale_gate.json"
    gate = write_plan_batch_gate(tmp_path, created_at="2000-01-01T00:00:00Z")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="stale"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_allows_stale_quota_gate_when_ttl_disabled(tmp_path: Path):
    output = tmp_path / "ttl_disabled.json"
    gate = write_plan_batch_gate(tmp_path, created_at="2000-01-01T00:00:00Z")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), quota_gate_ttl_seconds=0)
    manifest = run_calibration(args, env={}, client=client)

    assert manifest["status"] == "ok"
    assert manifest["guardrails"]["quota_gate"]["validation"]["ttl_seconds"] == 0
    assert any(call[0] == "create_request" for call in client.calls)


def test_run_calibration_rejects_wrong_target_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_target.json"
    gate = write_plan_batch_gate(tmp_path, target_operation="create-run")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="target_operation"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_quota_gate_modality_mismatch_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_modalities.json"
    gate = write_plan_batch_gate(tmp_path, modalities=["text"])
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, allow_paid_media=True, max_retries=0, modalities=("image",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="modalities"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_quota_gate_request_fingerprint_mismatch_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_fingerprint.json"
    gate = write_plan_batch_gate(tmp_path, request_fingerprint="not-the-text-calibrator-fingerprint")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))

    with pytest.raises(CalibrationUsageError, match="request_fingerprint"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_small_batch_with_text_mutation(tmp_path: Path):
    output = tmp_path / "real.json"
    gate = write_plan_batch_gate(tmp_path, modalities=["text"], request_fingerprint=calibration_request_fingerprint("text"))
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient())

    assert manifest["status"] == "ok"
    assert manifest["summary"]["read_steps"] == 5
    assert manifest["summary"]["mutating_steps"] == 1
    assert manifest["summary"]["modalities"] == ["text"]
    assert manifest["guardrails"]["quota_gate"]["validation"]["modalities"] == ["text"]
    assert manifest["guardrails"]["quota_gate"]["validation"]["request_fingerprint"] == calibration_request_fingerprint("text")
    assert "tp_syntheticsecret" not in json.dumps(manifest)


def test_run_calibration_persists_audited_quota_override_with_redaction(tmp_path: Path):
    output = tmp_path / "override.json"
    gate = write_plan_batch_gate(tmp_path, decision="stop")
    reason = "manual paid calibration approved with tp_syntheticsecret after external quota review"
    args = CalibrationArgs(
        execute=True,
        small_batch=True,
        include_mutating=True,
        max_retries=0,
        modalities=("text",),
        output=str(output),
        quota_gate_record=str(gate),
        allow_quota_override=True,
        quota_override_reason=reason,
    )
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient())

    quota_gate = manifest["guardrails"]["quota_gate"]
    assert manifest["status"] == "ok"
    assert quota_gate["decision"] == "override"
    assert quota_gate["gate_decision"] == "stop"
    assert quota_gate["override"]["used"] is True
    assert "[redacted]" in quota_gate["override"]["reason"]
    assert "tp_syntheticsecret" not in json.dumps(manifest)

    mutate_step = next(step for step in manifest["steps"] if step["kind"] == "mutate")
    private_record = json.loads(Path(mutate_step["private_record_path"]).read_text(encoding="utf-8"))
    assert private_record["quota_gate"]["decision"] == "override"
    assert private_record["request"]["preflight"]["quota_gate"]["override_used"] is True
    assert "tp_syntheticsecret" not in json.dumps(private_record)


def test_run_calibration_captures_quota_block_without_raw_secret(tmp_path: Path):
    output = tmp_path / "quota.json"
    gate = write_plan_batch_gate(tmp_path)
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate))
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient(quota_block=True))

    assert manifest["status"] == "partial"
    assert manifest["summary"]["quota_block_count"] == 1
    assert manifest["errors"][0]["quota"]["remaining"] == 0
    assert ("tp_" + "syntheticsecret") not in json.dumps(manifest)
