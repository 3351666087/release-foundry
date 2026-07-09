from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from packages.sdk.ashr_clone.calibrate import (
    CALIBRATION_MANIFEST_SCHEMA_VERSION,
    DEFAULT_QUOTA_GATE_TTL_SECONDS,
    FIELD_PARITY_PLAN_SCHEMA_VERSION,
    API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION,
    PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION,
    PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION,
    CalibrationArgs,
    CalibrationUsageError,
    build_api_calibration_readiness_packet,
    build_field_parity_plan,
    calibration_request_fingerprint,
    calibration_target_binding,
    main,
    parse_args,
    public_official_api_manifest_summary,
    public_official_api_manifest_summary_from_file,
    request_for_modality,
    run_calibration,
    selected_calibration_modalities,
    write_api_calibration_readiness_packet,
    write_public_official_api_manifest_summary,
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
    target_binding=None,
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
    if target_binding is not None:
        plan["target_binding"] = target_binding
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
    assert manifest["guardrails"]["output_policy"]["private_output_required"] is False
    assert manifest["guardrails"]["output_policy"]["sink"] == "nonprivate_file"
    assert output.exists()
    for step in manifest["steps"]:
        assert Path(step["private_record_path"]).exists()


def test_build_field_parity_plan_is_public_safe_and_env_only():
    args = CalibrationArgs(include_mutating=True, modalities=("text",))
    plan = build_field_parity_plan(args)
    plan_text = json.dumps(plan, sort_keys=True)

    assert plan["schema_version"] == FIELD_PARITY_PLAN_SCHEMA_VERSION
    assert plan["official_api_contract"]["auth_env_vars"] == ["ASHR_API_KEY", "ASHR_LABS_API_KEY"]
    assert plan["official_api_contract"]["key_material_source"] == "environment at execution time only"
    assert plan["official_api_contract"]["key_material_logged"] is False
    assert plan["execution_modes"]["default"] == "dry-run"
    assert plan["execution_modes"]["dry_run_calls_real_api"] is False
    assert plan["quota_gate"]["target_operation"] == "create-request"
    assert plan["quota_gate"]["request_fingerprints"] == {"text": calibration_request_fingerprint("text")}
    assert plan["summary"]["read_steps"] == 5
    assert plan["summary"]["mutating_steps"] == 1
    assert plan["summary"]["estimated_calls_dry_run"] == 0
    assert plan["summary"]["missing_observed_functions"] == []
    assert "Authorization" not in plan_text
    assert "Bearer" not in plan_text
    assert "tp_syntheticsecret" not in plan_text

    by_step = {step["step_id"]: step for step in plan["steps"]}
    assert by_step["init"]["observed_response_keys"]
    assert "request" in by_step["create-request-text"]["observed_response_keys"]


def test_build_field_parity_plan_describes_all_modality_shapes_without_raw_assets():
    args = CalibrationArgs(include_mutating=True)
    plan = build_field_parity_plan(args)
    plan_text = json.dumps(plan, sort_keys=True)

    assert plan["summary"]["modalities"] == ["audio", "file", "image", "text", "video"]
    assert {item["modality"] for item in plan["modality_matrix"]} == {"text", "image", "audio", "file", "video"}
    assert all(item["raw_asset_recorded_publicly"] is False for item in plan["modality_matrix"])
    assert all(item["request_shape"] is not None for item in plan["steps"] if item["kind"] == "mutate")
    assert "Authorization" not in plan_text
    assert "Bearer" not in plan_text
    assert "tp_syntheticsecret" not in plan_text


def test_run_calibration_execute_read_only_does_not_require_quota_gate(tmp_path: Path):
    output = tmp_path / "read_only_real.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, max_retries=0, output=str(output), allow_nonprivate_output=True)
    manifest = run_calibration(args, env={}, client=client)

    assert manifest["status"] == "ok"
    assert manifest["summary"]["read_steps"] == 5
    assert manifest["summary"]["mutating_steps"] == 0
    assert manifest["guardrails"]["output_policy"]["private_output_required"] is True
    assert manifest["guardrails"]["output_policy"]["nonprivate_output_override_used"] is True
    assert all(call[0] != "create_request" for call in client.calls)
    assert manifest["guardrails"]["quota_gate"] is None


def test_run_calibration_mutating_execute_requires_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "missing_gate.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="quota-gate-record"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_mutating_execute_requires_explicit_modality_before_calls(tmp_path: Path):
    output = tmp_path / "implicit_modalities.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(
        execute=True,
        small_batch=True,
        include_mutating=True,
        allow_paid_media=True,
        max_retries=0,
        output=str(output),
        quota_gate_record=str(write_plan_batch_gate(tmp_path)),
        allow_nonprivate_output=True,
    )

    with pytest.raises(CalibrationUsageError, match="explicit --modality"):
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
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(read_only_record), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="plan-batch quota gate record"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_stop_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "stop_gate.json"
    gate = write_plan_batch_gate(tmp_path, decision="stop")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

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
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="requires reviewed quota/reset evidence"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_stale_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "stale_gate.json"
    gate = write_plan_batch_gate(tmp_path, created_at="2000-01-01T00:00:00Z")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="stale"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_allows_stale_quota_gate_when_ttl_disabled(tmp_path: Path):
    output = tmp_path / "ttl_disabled.json"
    gate = write_plan_batch_gate(tmp_path, created_at="2000-01-01T00:00:00Z")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), quota_gate_ttl_seconds=0, allow_nonprivate_output=True)
    manifest = run_calibration(args, env={}, client=client)

    assert manifest["status"] == "ok"
    assert manifest["guardrails"]["quota_gate"]["validation"]["ttl_seconds"] == 0
    assert any(call[0] == "create_request" for call in client.calls)


def test_run_calibration_rejects_wrong_target_quota_gate_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_target.json"
    gate = write_plan_batch_gate(tmp_path, target_operation="create-run")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="target_operation"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_protected_output_requires_private_dir_before_calls(tmp_path: Path):
    output = tmp_path / "read_only_real.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, max_retries=0, output=str(output))

    with pytest.raises(CalibrationUsageError, match="docs/evidence/private_refs"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_quota_gate_protected_output_blocks_before_gate_read(tmp_path: Path):
    output = tmp_path / "manifest.json"
    missing_gate = tmp_path / "missing-gate.json"
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(missing_gate))

    with pytest.raises(CalibrationUsageError, match="docs/evidence/private_refs"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_protected_print_record_blocks_before_key_lookup(tmp_path: Path):
    output = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "private_refs" / "pytest_print_record_block.json"
    if output.exists():
        output.unlink()
    client = FakeCalibrationClient()
    args = parse_args(["--execute", "--small-batch", "--max-retries", "0", "--output", str(output), "--print-record"])

    with pytest.raises(CalibrationUsageError, match="--print-record"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_quota_gate_modality_mismatch_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_modalities.json"
    gate = write_plan_batch_gate(tmp_path, modalities=["text"])
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, allow_paid_media=True, max_retries=0, modalities=("image",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="modalities"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_rejects_quota_gate_request_fingerprint_mismatch_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_fingerprint.json"
    gate = write_plan_batch_gate(tmp_path, request_fingerprint="not-the-text-calibrator-fingerprint")
    client = FakeCalibrationClient()
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)

    with pytest.raises(CalibrationUsageError, match="request_fingerprint"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_accepts_matching_quota_gate_target_binding(tmp_path: Path):
    output = tmp_path / "target_binding.json"
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), allow_nonprivate_output=True)
    gate = write_plan_batch_gate(tmp_path, modalities=["text"], target_binding=calibration_target_binding("text", args))
    args.quota_gate_record = str(gate)

    manifest = run_calibration(args, env={}, client=FakeCalibrationClient())

    validation = manifest["guardrails"]["quota_gate"]["validation"]
    assert manifest["status"] == "ok"
    assert validation["target_binding"]["fingerprint"] == calibration_target_binding("text", args)["fingerprint"]
    assert validation["target_binding"]["raw_request_not_recorded"] is True


def test_run_calibration_rejects_quota_gate_target_binding_mismatch_before_calls(tmp_path: Path):
    output = tmp_path / "wrong_target_binding.json"
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), allow_nonprivate_output=True)
    target_binding = calibration_target_binding("text", args)
    target_binding["allow_non_text_inputs"] = False
    gate = write_plan_batch_gate(tmp_path, modalities=["text"], target_binding=target_binding)
    args.quota_gate_record = str(gate)
    client = FakeCalibrationClient()

    with pytest.raises(CalibrationUsageError, match="target_binding"):
        run_calibration(args, env={}, client=client)

    assert client.calls == []
    assert not output.exists()


def test_run_calibration_small_batch_with_text_mutation(tmp_path: Path):
    output = tmp_path / "real.json"
    gate = write_plan_batch_gate(tmp_path, modalities=["text"], request_fingerprint=calibration_request_fingerprint("text"))
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)
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
        allow_nonprivate_output=True,
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
    args = CalibrationArgs(execute=True, small_batch=True, include_mutating=True, max_retries=0, modalities=("text",), output=str(output), quota_gate_record=str(gate), allow_nonprivate_output=True)
    manifest = run_calibration(args, env={"ASHR_API_KEY": "tp_syntheticsecret"}, client=FakeCalibrationClient(quota_block=True))

    assert manifest["status"] == "partial"
    assert manifest["summary"]["quota_block_count"] == 1
    assert manifest["errors"][0]["quota"]["remaining"] == 0
    assert ("tp_" + "syntheticsecret") not in json.dumps(manifest)

def test_api_calibration_readiness_packet_builder_is_public_safe():
    packet = build_api_calibration_readiness_packet()
    safety = packet["public_safety"]
    gap_ids = {gap["id"] for gap in packet["gaps"]}
    next_read_only = packet["next_read_only_calibration"]
    target_ids = {target["id"] for target in next_read_only["target_shape_groups"]}
    payload = json.dumps(packet, sort_keys=True)

    assert packet["schema_version"] == API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION
    assert safety["raw_key_material_present"] is False
    assert safety["auth_header_present"] is False
    assert safety["contains_raw_payload_response"] is False
    assert safety["contains_private_evidence_contents"] is False
    assert safety["private_evidence_references_only"] is True
    assert packet["observed_surface"]["read_only_missing_from_field_map"] == []
    assert packet["readiness"]["next_read_only_calibration_ready"] is True
    assert target_ids == {"error_shape_refresh", "usage_shape_refresh", "quota_shape_refresh"}
    assert next_read_only["constraints"]["env_only_auth_material"] is True
    assert next_read_only["constraints"]["mutating_calls_allowed"] is False
    assert next_read_only["constraints"]["include_mutating_allowed"] is False
    assert next_read_only["constraints"]["paid_media_allowed"] is False
    assert "--include-mutating" not in next_read_only["commands"]["real_read_only_private"]
    assert "--allow-paid-media" not in next_read_only["commands"]["real_read_only_private"]
    assert "--execute --small-batch --max-retries 0" in next_read_only["commands"]["real_read_only_private"]
    assert next_read_only["commands"]["real_read_only_private"].count("docs/evidence/private_refs/") == 1
    assert "mutating_create_request_quota_gate" in gap_ids
    assert "hosted_surface_not_commercially_complete" in gap_ids
    assert "Bearer " not in payload
    assert "tp_syntheticsecret" not in payload


def test_api_calibration_readiness_packet_artifact_matches_schema_and_keeps_private_refs_public():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "docs" / "a1" / "schemas" / "api_calibration_readiness_packet.schema.json").read_text(encoding="utf-8"))
    packet = json.loads((root / "docs" / "a1" / "api_calibration" / "official_api_readiness_packet.json").read_text(encoding="utf-8"))
    payload = json.dumps(packet, sort_keys=True)

    assert schema["properties"]["schema_version"]["const"] == API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION
    for field in schema["required"]:
        assert field in packet
    for field in schema["properties"]["public_safety"]["required"]:
        assert field in packet["public_safety"]
    for field in schema["properties"]["next_read_only_calibration"]["required"]:
        assert field in packet["next_read_only_calibration"]
    assert packet["public_safety"]["raw_key_material_present"] is False
    assert packet["public_safety"]["auth_header_present"] is False
    assert packet["public_safety"]["private_evidence_root"] == "docs/evidence/private_refs"
    assert packet["readiness"]["next_read_only_calibration_ready"] is True
    assert {target["id"] for target in packet["next_read_only_calibration"]["target_shape_groups"]} == {"error_shape_refresh", "usage_shape_refresh", "quota_shape_refresh"}
    assert packet["next_read_only_calibration"]["constraints"]["env_only_auth_material"] is True
    assert packet["next_read_only_calibration"]["constraints"]["never_print_or_store_key"] is True
    assert packet["next_read_only_calibration"]["constraints"]["raw_response_payload_publication_allowed"] is False
    assert "docs/evidence/private_refs" in payload
    assert "response_headers" not in payload
    assert "authorization" not in payload.lower()
    assert "bearer " not in payload.lower()
    assert "--include-mutating" not in packet["next_read_only_calibration"]["commands"]["real_read_only_private"]
    assert "--allow-paid-media" not in packet["next_read_only_calibration"]["commands"]["real_read_only_private"]


def test_public_official_api_manifest_summary_keeps_only_redacted_summary_fields():
    manifest = {
        "schema_version": CALIBRATION_MANIFEST_SCHEMA_VERSION,
        "mode": "small-batch",
        "dry_run": False,
        "status": "ok",
        "started_at": "2026-07-09T13:39:39Z",
        "ended_at": "2026-07-09T13:39:40Z",
        "duration_ms": 1000,
        "field_map_version": "a1-api-calibration-2026-07-04",
        "env": {"auth_env_present": ["ASHR_API_KEY"], "base_url": "https://api.ashr.io/testing-platform-api?api_key=tp_syntheticsecret"},
        "guardrails": {
            "raw_records_private": True,
            "execute_requires_small_batch": True,
            "mutating_requires_include_mutating": True,
            "paid_media_requires_allow_paid_media": True,
            "mutating_execute_requires_quota_gate": True,
            "output_policy": {
                "private_output_required": True,
                "output_is_private": True,
                "sink": "private_file",
                "private_root": "docs/evidence/private_refs",
                "full_record_stdout_blocked": True,
            },
        },
        "summary": {"total_steps": 1, "read_steps": 1, "mutating_steps": 0, "ok_or_planned_steps": 1, "error_steps": 0, "estimated_calls": 1, "modalities": [], "quota_block_count": 0},
        "steps": [
            {
                "step_id": "list_agents",
                "kind": "read",
                "function": "list_agents",
                "dry_run": False,
                "status": "ok",
                "status_code": 200,
                "attempts": 1,
                "estimated_calls": 1,
                "response_keys": ["agents", "private_payload"],
                "response_headers_keys": ["authorization", "x-request-id"],
                "response_summary_keys": ["count"],
                "response": {"private_payload": "customer-private-body", "api_key": "tp_syntheticsecret"},
                "request": {"params": {"authorization": "Bearer tp_syntheticsecret"}},
                "private_record_path": "docs/evidence/private_refs/raw_record.json",
                "top_counts": {"agents": 1},
            }
        ],
        "errors": [],
    }

    summary = public_official_api_manifest_summary(manifest, source_path="docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json")
    payload = json.dumps(summary, sort_keys=True)

    assert summary["schema_version"] == PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION
    assert summary["source_private_manifest"] == "docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json"
    assert summary["source_private_manifest_present"] is True
    assert summary["env"]["auth_env_present_count"] == 1
    assert summary["env"]["base_url_host"] == "api.ashr.io"
    assert summary["summary"]["total_steps"] == 1
    assert summary["step_summaries"][0]["response_keys"] == ["agents", "private_payload"]
    assert summary["public_safety"]["redacted_summary_fields_only"] is True
    assert "response_headers" not in payload
    assert "private_record_path" not in payload
    assert "customer-private-body" not in payload
    assert "tp_syntheticsecret" not in payload
    assert "ASHR_API_KEY" not in payload
    assert "Bearer" not in payload
    assert "authorization" not in payload.lower()
    assert "api_key" not in payload.lower()


def test_public_official_api_manifest_summary_from_missing_file_is_public_safe(tmp_path: Path):
    summary = public_official_api_manifest_summary_from_file(tmp_path / "missing_private_manifest.json")
    payload = json.dumps(summary, sort_keys=True)

    assert summary["schema_version"] == PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION
    assert summary["source_private_manifest_present"] is False
    assert summary["status"] == "missing"
    assert summary["summary"]["total_steps"] == 0
    assert summary["public_safety"]["raw_payload_values_included"] is False
    assert "response_headers" not in payload
    assert "authorization" not in payload.lower()
    assert "bearer " not in payload.lower()


def test_parse_public_safe_manifest_summary_command_defaults_to_public_artifact():
    args = parse_args(["summarize-private-manifest", "--input", "docs/evidence/private_refs/private.json"])

    assert args.command == "summarize-private-manifest"
    assert args.input_manifest == "docs/evidence/private_refs/private.json"
    assert args.output.endswith("official_api_readonly_manifest_summary.json")


def test_write_public_official_api_manifest_summary_redacts_private_manifest_file(tmp_path: Path):
    private_manifest = tmp_path / "private_refs" / "manifest.json"
    public_summary = tmp_path / "official_api_readonly_manifest_summary.json"
    private_manifest.parent.mkdir()
    private_manifest.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_MANIFEST_SCHEMA_VERSION,
                "mode": "small-batch",
                "dry_run": False,
                "status": "ok",
                "env": {"auth_env_present": ["ASHR_API_KEY"], "base_url": "https://api.ashr.io/testing-platform-api?api_key=tp_syntheticsecret"},
                "guardrails": {"raw_records_private": True, "output_policy": {"private_output_required": True, "output_is_private": True, "sink": "private_file"}},
                "summary": {"total_steps": 1, "read_steps": 1, "mutating_steps": 0, "ok_or_planned_steps": 1, "error_steps": 0, "estimated_calls": 1, "modalities": [], "quota_block_count": 0},
                "steps": [
                    {
                        "step_id": "list_agents",
                        "kind": "read",
                        "function": "list_agents",
                        "dry_run": False,
                        "status": "ok",
                        "response_keys": ["agents", "private_payload"],
                        "response": {"private_payload": "customer-private-body", "api_key": "tp_syntheticsecret"},
                        "private_record_path": "docs/evidence/private_refs/raw_record.json",
                    }
                ],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    summary = write_public_official_api_manifest_summary(input_path=private_manifest, output_path=public_summary)
    persisted = public_summary.read_text(encoding="utf-8")

    assert summary["source_private_manifest_present"] is True
    assert summary["summary"]["total_steps"] == 1
    assert "customer-private-body" not in persisted
    assert "tp_syntheticsecret" not in persisted
    assert "ASHR_API_KEY" not in persisted
    assert "private_record_path" not in persisted


def test_write_readiness_packet_command_is_dry_run_public_safe(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "official_api_readiness_packet.json"

    rc = main(["write-readiness-packet", "--output", str(output), "--evidence-index", "none"])
    packet = json.loads(output.read_text(encoding="utf-8"))
    payload = json.dumps(packet, sort_keys=True)

    assert rc == 0
    assert packet["schema_version"] == API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION
    assert packet["readiness"]["public_packet_ready"] is True
    assert packet["execution_guardrails"]["default_mode"] == "dry-run"
    assert packet["public_safety"]["raw_key_material_present"] is False
    assert packet["source_field_map"] == str((root / "docs" / "a1" / "api_calibration" / "real_api_response_field_map.json").relative_to(root)).replace("\\", "/")
    assert "tp_syntheticsecret" not in payload
    assert "Bearer" not in payload
    assert "api_key=" not in payload.lower()


def test_write_api_calibration_readiness_packet_helper_writes_artifact(tmp_path: Path):
    output = tmp_path / "readiness.json"
    packet = write_api_calibration_readiness_packet(CalibrationArgs(command="write-readiness-packet"), output_path=output, evidence_index_path=None)

    assert output.exists()
    assert packet["readiness"]["next_read_only_calibration_ready"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION
