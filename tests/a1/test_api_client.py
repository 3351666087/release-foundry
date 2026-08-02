import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from releasefoundry.api_client import ReleaseFoundryApiClient, ReleaseFoundryApiError, build_default_request_input_schema, redact_sensitive, redact_text, summarize_generation_request  # noqa: E402
from services.runner import api_probe  # noqa: E402


def probe_plan_gate_payload(decision="go", *, target_operation="create-request", created_at=None, request=None, request_schema=None, batch_size=None):
    request = request if request is not None else {"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}
    preflight = api_probe.summarize_generation_request(request) if target_operation == "create-request" else None
    small_batch_size = 1
    inferred_batch_size = api_probe._inferred_batch_size(preflight, small_batch_size, batch_size)
    target_binding = api_probe.build_target_binding(
        target_operation=target_operation,
        request=request if target_operation == "create-request" else None,
        request_input_schema=request_schema,
        request_input_schema_source="file" if request_schema is not None else "client_default" if target_operation == "create-request" else "not_applicable",
        allow_media_generation=False,
        allow_non_text_inputs=False,
        max_request_variations=1,
        small_batch_size=small_batch_size,
        batch_size=inferred_batch_size,
        modality_sequence=api_probe.build_modality_sequence(preflight),
    )
    gate = {
        "decision": decision,
        "source": "quota-record",
        "quota_or_reset_evidence_present": True,
        "reset": {"known": False, "wait_hint_present": False, "header_keys": ["x-ratelimit-remaining"]},
        "can_enter_small_batch": decision == "go",
        "can_enter_batch": decision == "go",
    }
    return {
        "schema_version": api_probe.API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
        "function": "plan_batch",
        "response": {
            "plan": {
                "schema_version": api_probe.API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
                "target_operation": target_operation,
                "created_at": created_at or api_probe.utc_now(),
                "target_binding": target_binding,
                "quota_stop_go": gate,
            }
        },
    }


def test_dry_run_records_plan_without_api_key(tmp_path):
    output = tmp_path / "dry_run.json"
    client = ReleaseFoundryApiClient(**{"api_" + "key": None})

    record = client.list_datasets(limit=3, output_path=output, dry_run=True)

    assert record["dry_run"] is True
    assert record["status"] == "planned"
    assert record["attempts"] == 0
    assert record["request"]["function"] == "list_datasets"
    assert record["request"]["params"]["limit"] == 3
    assert json.loads(output.read_text(encoding="utf-8")) == record


def test_execute_uses_transport_and_redacts_authorization(tmp_path):
    seen = []

    def transport(url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8"))
        seen.append({"url": url, "headers": dict(headers), "body": payload, "timeout": timeout})
        if payload["function"] == "init":
            return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}', {"x-ratelimit-remaining": "9"}
        return 200, b'{"status":"ok","datasets":[{"id":42,"name":"Demo"}]}', {"retry-after": "1"}

    output = tmp_path / "real.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, timeout=7)

    record = client.list_datasets(limit=1, output_path=output, dry_run=False)

    assert seen[0]["headers"]["Authorization"] == "Bearer tp_test_secret"
    assert seen[0]["body"]["function"] == "init"
    assert seen[1]["body"]["function"] == "list_datasets"
    assert seen[1]["body"]["tenant_id"] == 2
    assert seen[1]["timeout"] == 7
    assert record["status"] == "ok"
    assert record["response"]["datasets"][0]["id"] == 42
    assert record["response_headers"] == {"retry-after": "1"}
    assert "tp_test_secret" not in output.read_text(encoding="utf-8")


def test_from_env_accepts_official_releasefoundry_names(monkeypatch):
    monkeypatch.delenv("RELEASEFOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("RELEASEFOUNDRY_API_KEY", "tp_labs_secret")
    monkeypatch.setenv("RELEASEFOUNDRY_BASE_URL", "https://example.invalid/releasefoundry")

    client = ReleaseFoundryApiClient.from_env()

    assert repr(client) == "ReleaseFoundryApiClient(base_url='https://example.invalid/releasefoundry', api_key=set)"


def test_health_check_uses_official_keep_alive_function(tmp_path):
    output = tmp_path / "health_check.json"
    client = ReleaseFoundryApiClient(**{"api_" + "key": None})

    record = client.health_check(output_path=output, dry_run=True)

    assert record["status"] == "planned"
    assert record["request"]["function"] == "keep_alive"
    assert record["request"]["estimated_calls"] == 1
    assert record["request"]["mutates"] is False


def test_list_agents_execute_uses_official_function_without_session(tmp_path):
    calls = []

    def transport(_url, _headers, body, _timeout):
        payload = json.loads(body.decode("utf-8"))
        calls.append(payload)
        return 200, b'{"status":"ok","agents":[]}'

    output = tmp_path / "list_agents.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.list_agents(output_path=output, dry_run=False)

    assert record["status"] == "ok"
    assert record["response"]["agents"] == []
    assert [call["function"] for call in calls] == ["list_agents"]
    assert json.loads(output.read_text(encoding="utf-8"))["request"]["function"] == "list_agents"


def test_retryable_status_retries_then_succeeds():
    calls = []

    def transport(_url, _headers, _body, _timeout):
        calls.append("call")
        if len(calls) == 1:
            return 429, b'{"status":"error","message":"rate limited"}'
        return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=2, retry_backoff_seconds=0)

    record = client.init(dry_run=False)

    assert record["attempts"] == 2
    assert record["status_code"] == 200


def test_non_retryable_status_writes_error_record(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 401, b'{"status":"error","message":"bad key","api_key":"tp_secret"}'

    output = tmp_path / "error.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=3)

    try:
        client.init(output_path=output, dry_run=False)
    except ReleaseFoundryApiError as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected ReleaseFoundryApiError")

    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["attempts"] == 1
    assert record["status"] == "error"
    assert record["error"]["response"]["api_key"] == "[redacted]"
    assert record["error"]["error_kind"] == "http"


def test_api_error_with_status_ok_has_api_error_kind(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"error","message":"dataset not found"}'

    output = tmp_path / "api_error.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.get_dataset(0, output_path=output, dry_run=False)
    except ReleaseFoundryApiError as exc:
        assert exc.status_code == 200
        assert exc.error_kind == "api"
    else:
        raise AssertionError("expected ReleaseFoundryApiError")

    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["status_code"] == 200
    assert record["error"]["error_kind"] == "api"


def test_error_message_text_is_redacted_in_file_and_exception(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"error","message":"bad key tp_leaked_secret for owner@example.com"}'

    output = tmp_path / "api_error.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.get_dataset(0, output_path=output, dry_run=False)
    except ReleaseFoundryApiError as exc:
        assert "tp_leaked_secret" not in str(exc)
        assert "owner@example.com" not in str(exc)
        assert "[redacted]" in str(exc)
    else:
        raise AssertionError("expected ReleaseFoundryApiError")

    text = output.read_text(encoding="utf-8")
    assert "tp_leaked_secret" not in text
    assert "owner@example.com" not in text
    assert "[redacted]" in text


def test_poll_run_dry_run_records_estimated_calls(tmp_path):
    output = tmp_path / "poll_run.json"
    client = ReleaseFoundryApiClient(**{"api_" + "key": None})

    record = client.poll_run(run_id=123, timeout_seconds=60, poll_interval_seconds=20, output_path=output, dry_run=True)

    assert record["status"] == "planned"
    assert record["request"]["function"] == "poll_run"
    assert record["request"]["estimated_calls"] == 4
    assert record["request"]["params"]["run_id"] == 123


def test_poll_run_execute_accepts_real_run_result_shape(tmp_path):
    calls = []

    def transport(_url, _headers, _body, _timeout):
        calls.append(json.loads(_body.decode("utf-8")))
        return 200, json.dumps(
            {
                "status": "ok",
                "run": {
                    "id": 123,
                    "result": {
                        "aggregate_metrics": {"trace_completeness": 1.0},
                        "total_cases": 3,
                        "status": "completed_with_errors",
                    },
                },
            }
        ).encode("utf-8")

    output = tmp_path / "poll_run_real_shape.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport)

    record = client.poll_run(run_id=123, timeout_seconds=1, poll_interval_seconds=0, output_path=output, dry_run=False)

    assert record["status"] == "ok"
    assert record["attempts"] == 1
    assert calls[0]["function"] == "get_run"
    assert json.loads(output.read_text(encoding="utf-8"))["response"]["run"]["result"]["total_cases"] == 3


def test_poll_request_execute_stops_on_completed_response(tmp_path):
    calls = []

    def transport(_url, _headers, _body, _timeout):
        calls.append(json.loads(_body.decode("utf-8")))
        if len(calls) == 1:
            return 200, b'{"status":"ok","request":{"id":7,"request_status":"pending"}}'
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"completed"}}'

    output = tmp_path / "poll_request.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport)

    record = client.poll_request(request_id=7, timeout_seconds=1, poll_interval_seconds=0, output_path=output, dry_run=False)

    assert record["status"] == "ok"
    assert record["attempts"] == 2
    assert calls[0]["function"] == "get_request"
    assert json.loads(output.read_text(encoding="utf-8"))["response"]["request"]["request_status"] == "completed"


def test_get_request_failed_response_records_safe_failure_summary(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"failed","request":{"_failure":{"at":"2026-07-04T00:00:00Z","error":"bad media key tp_secret for owner@example.com"}}}}'

    output = tmp_path / "get_request_failed.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.get_request(7, output_path=output, dry_run=False)

    summary = record["response_summary"]["request_failure"]
    nested_failure = summary["failure_sources"]["request._failure"]
    assert summary["request_status"] == "failed"
    assert summary["top_level_failure_like_keys"] == []
    assert summary["nested_request_keys"] == ["_failure"]
    assert nested_failure["keys"] == ["at", "error"]
    assert nested_failure["fields"]["error"]["type"] == "string"
    assert nested_failure["fields"]["error"]["length"] > 0
    text = output.read_text(encoding="utf-8")
    assert "tp_secret" not in text
    assert "owner@example.com" not in text


def test_get_request_completed_with_details_does_not_record_failure_summary(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"completed","requestor_details":{"name":"Owner"}}}'

    output = tmp_path / "get_request_completed.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.get_request(7, output_path=output, dry_run=False)

    assert "response_summary" not in record
    assert "response_summary" not in json.loads(output.read_text(encoding="utf-8"))


def test_poll_request_failed_response_raises_with_failure_summary(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"failed","request":{"_failure":{"at":"worker","error":"media processor failed"}}}}'

    output = tmp_path / "poll_request_failed.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.poll_request(request_id=7, timeout_seconds=1, poll_interval_seconds=0, output_path=output, dry_run=False)
    except ReleaseFoundryApiError as exc:
        assert str(exc) == "request failed"
    else:
        raise AssertionError("expected failed poll request")

    record = json.loads(output.read_text(encoding="utf-8"))
    failure_summary = record["error"]["failure_summary"]
    assert record["status"] == "error"
    assert record["attempts"] == 1
    assert record["error"]["message"] == "request failed"
    assert failure_summary == record["response_summary"]["request_failure"]
    assert failure_summary["failure_sources"]["request._failure"]["fields"]["error"]["type"] == "string"


def test_create_request_dry_run_records_mutating_plan(tmp_path):
    output = tmp_path / "create_request.json"
    client = ReleaseFoundryApiClient(api_key=None)

    record = client.create_request(request_name="Tiny calibration", request={"agent": {"name": "Mock"}, "context": {"domain": "tests"}}, output_path=output, dry_run=True)

    assert record["status"] == "planned"
    assert record["request"]["function"] == "create_request"
    assert record["request"]["mutates"] is True
    assert record["request"]["params"]["request_name"] == "Tiny calibration"


def test_create_request_records_preflight_summary(tmp_path):
    output = tmp_path / "create_request.json"
    client = ReleaseFoundryApiClient(api_key=None)

    record = client.create_request(
        request_name="Tiny calibration",
        request={"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}},
        output_path=output,
        dry_run=True,
    )

    assert record["request"]["preflight"]["num_variations"] == 1
    assert record["response"]["plan"]["preflight"]["media_generation_enabled"] is False
    assert record["response"]["plan"]["preflight"]["request_input_schema_source"] == "client_default"


def test_create_request_uses_default_request_input_schema_for_sdk_parity(tmp_path):
    calls = []

    def transport(_url, _headers, body, _timeout):
        payload = json.loads(body.decode("utf-8"))
        calls.append(payload)
        if payload["function"] == "init":
            return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"pending"}}'

    output = tmp_path / "create_request.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.create_request(
        request_name="Tiny calibration",
        request={"agent": {"name": "Mock", "tools": [{"name": "lookup_order"}]}, "test_config": {"num_variations": 1}},
        output_path=output,
        dry_run=False,
    )

    sent = calls[1]
    assert record["status"] == "ok"
    assert sent["function"] == "create_request"
    assert sent["request_input_schema"]["type"] == "object"
    assert sent["request_input_schema"]["additionalProperties"] is True
    assert sent["request_input_schema"]["tools"] == [{"name": "lookup_order"}]


def test_create_request_preserves_explicit_request_input_schema(tmp_path):
    calls = []
    explicit_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def transport(_url, _headers, body, _timeout):
        payload = json.loads(body.decode("utf-8"))
        calls.append(payload)
        if payload["function"] == "init":
            return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"pending"}}'

    output = tmp_path / "create_request.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.create_request(
        request_name="Explicit schema",
        request={"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}},
        request_input_schema=explicit_schema,
        output_path=output,
        dry_run=False,
    )

    assert record["status"] == "ok"
    assert calls[1]["request_input_schema"] == explicit_schema
    assert json.loads(output.read_text(encoding="utf-8"))["request"]["params"]["request_input_schema"]["keys"] == ["properties", "required", "type"]
    assert json.loads(output.read_text(encoding="utf-8"))["request"]["preflight"]["request_input_schema_source"] == "file"


def test_create_request_record_summarizes_request_without_raw_prompt(tmp_path):
    calls = []
    marker = "DO_NOT_RECORD_RAW_PROMPT"

    def transport(_url, _headers, body, _timeout):
        payload = json.loads(body.decode("utf-8"))
        calls.append(payload)
        if payload["function"] == "init":
            return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"pending"}}'

    output = tmp_path / "create_request.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    client.create_request(
        request_name="Raw marker",
        request={
            "agent": {"name": "Mock", "accepted_inputs": {"text": True}},
            "context": {"scenario_context": marker},
            "generation_options": {"generate_audio": False},
            "test_config": {"num_variations": 1},
        },
        output_path=output,
        dry_run=False,
    )

    assert calls[1]["request"]["context"]["scenario_context"] == marker
    text = output.read_text(encoding="utf-8")
    assert marker not in text
    record = json.loads(text)
    assert record["request"]["params"]["request"]["top_level_keys"] == ["agent", "context", "generation_options", "test_config"]
    assert record["request"]["params"]["preflight_summary"]["request_input_schema_source"] == "client_default"


def test_direct_sdk_create_request_requires_zero_retries_for_real_execution():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport)

    try:
        client.create_request(request_name="Blocked", request={"agent": {"name": "Mock"}}, dry_run=False)
    except ValueError as exc:
        assert "max_retries=0" in str(exc)
    else:
        raise AssertionError("expected direct create_request retry guardrail")


def test_direct_sdk_create_request_blocks_unknown_variations_before_transport():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.create_request(request_name="Blocked", request={"agent": {"name": "Mock"}}, dry_run=False)
    except ValueError as exc:
        assert "num_variations is unknown" in str(exc)
    else:
        raise AssertionError("expected unknown num_variations guardrail")


def test_direct_sdk_create_request_blocks_media_generation_before_transport():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.create_request(
            request_name="Blocked",
            request={"generation_options": {"generate_images": True}, "test_config": {"num_variations": 1}},
            dry_run=False,
        )
    except ValueError as exc:
        assert "--allow-media-generation" in str(exc)
    else:
        raise AssertionError("expected media generation guardrail")


def test_direct_sdk_create_request_blocks_non_text_inputs_before_transport():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.create_request(
            request_name="Blocked",
            request={"agent": {"accepted_inputs": {"text": True, "audio": True}}, "test_config": {"num_variations": 1}},
            dry_run=False,
        )
    except ValueError as exc:
        assert "--allow-non-text-inputs" in str(exc)
    else:
        raise AssertionError("expected non-text input guardrail")


def test_direct_sdk_create_request_blocks_large_variation_count_before_transport():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.create_request(
            request_name="Blocked",
            request={"test_config": {"num_variations": 2}},
            dry_run=False,
            max_request_variations=1,
        )
    except ValueError as exc:
        assert "num_variations=2" in str(exc)
    else:
        raise AssertionError("expected variation count guardrail")


def test_direct_sdk_create_request_allows_media_when_explicit_flags_are_set(tmp_path):
    calls = []

    def transport(_url, _headers, body, _timeout):
        payload = json.loads(body.decode("utf-8"))
        calls.append(payload)
        if payload["function"] == "init":
            return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'
        return 200, b'{"status":"ok","request":{"id":7,"request_status":"pending"}}'

    output = tmp_path / "media_allowed.json"
    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    record = client.create_request(
        request_name="Allowed",
        request={
            "agent": {"accepted_inputs": {"text": True, "image": True}},
            "generation_options": {"generate_images": True},
            "test_config": {"num_variations": 1},
        },
        output_path=output,
        dry_run=False,
        allow_media_generation=True,
        allow_non_text_inputs=True,
    )

    assert record["status"] == "ok"
    assert [call["function"] for call in calls] == ["init", "create_request"]
    assert calls[1]["request_input_schema"]["properties"]["schema_version"]["const"] == "releasefoundry.agent_input.v1"


def test_direct_sdk_create_run_requires_zero_retries_for_real_execution():
    def transport(_url, _headers, _body, _timeout):
        raise AssertionError("transport should not be called")

    client = ReleaseFoundryApiClient(api_key="tp_test_secret", transport=transport)

    try:
        client.create_run(dataset_id=1, result={"status": "completed"}, dry_run=False)
    except ValueError as exc:
        assert "max_retries=0" in str(exc)
    else:
        raise AssertionError("expected direct create_run retry guardrail")


def test_build_default_request_input_schema_is_permissive_and_media_safe():
    schema = build_default_request_input_schema({"agent": {"tools": [{"name": "inspect_attachment"}]}})

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True
    assert schema["tools"] == [{"name": "inspect_attachment"}]
    assert "properties" not in schema


def test_build_default_request_input_schema_advertises_agent_input_parts_for_media():
    schema = build_default_request_input_schema(
        {
            "agent": {
                "accepted_inputs": {
                    "text": True,
                    "image": True,
                    "audio": {"enabled": True},
                    "file": True,
                    "video": True,
                }
            }
        }
    )

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True
    assert schema["properties"]["schema_version"]["const"] == "releasefoundry.agent_input.v1"
    assert sorted(schema["properties"].keys()) == ["metadata", "parts", "schema_version", "text"]
    part_schema = schema["$defs"]["agent_input_part"]
    media_part = part_schema["oneOf"][1]
    assert media_part["properties"]["type"]["enum"] == ["image", "audio", "file", "video"]


def test_build_default_request_input_schema_matches_non_text_only_inputs():
    request = {"agent": {"accepted_inputs": {"text": False, "image": True}}}
    schema = build_default_request_input_schema(request)
    preflight = summarize_generation_request(request)

    assert schema["$defs"]["agent_input_part"]["properties"]["type"]["enum"] == ["image"]
    assert preflight["agent_input_part_types"] == ["image"]
    assert preflight["agent_input_schema_version"] == "releasefoundry.agent_input.v1"


def test_create_request_record_summarizes_non_text_only_schema_parts(tmp_path):
    request = {"agent": {"accepted_inputs": {"text": False, "image": True}}, "test_config": {"num_variations": 1}}
    output = tmp_path / "image_only_probe.json"
    client = ReleaseFoundryApiClient(**{"api_" + "key": None})

    record = client.create_request(
        request_name="Image-only dry run",
        request=request,
        output_path=output,
        dry_run=True,
    )

    schema_summary = record["request"]["params"]["request_input_schema"]
    assert schema_summary["agent_input_part_types"] == ["image"]
    assert json.loads(output.read_text(encoding="utf-8"))["request"]["params"]["request_input_schema"]["agent_input_part_types"] == ["image"]


def test_api_probe_create_request_dry_run_adds_preflight(tmp_path):
    request_file = tmp_path / "request.json"
    output = tmp_path / "probe.json"
    request_file.write_text(
        json.dumps(
            {
                "agent": {"name": "Mock", "accepted_inputs": {"text": True, "audio": False}},
                "generation_options": {"generate_audio": False, "generate_images": False},
                "test_config": {"num_variations": 1},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.runner.api_probe",
            "create-request",
            "--request-name",
            "Tiny",
            "--request-file",
            str(request_file),
            "--output",
            str(output),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["request"]["preflight"]["num_variations"] == 1
    assert record["request"]["preflight"]["media_generation_enabled"] is False
    assert record["request"]["preflight"]["small_batch"] is True
    assert record["request"]["preflight"]["request_input_schema_source"] == "client_default"
    assert record["request"]["preflight"]["batch_plan"]["phase_order"] == ["dry-run", "small-batch", "batch"]
    assert record["request"]["preflight"]["batch_plan"]["quota_decision"] == "wait"
    assert record["request"]["preflight"]["batch_plan"]["modality_order"] == ["text"]
    assert record["response"]["plan"]["batch_plan"]["phases"][1]["phase"] == "small-batch"
    assert record["request"]["params"]["request_input_schema"]["type"] == "object"


def test_api_probe_batch_plan_sequences_text_then_media_without_raw_request():
    request = {
        "agent": {"name": "Mock", "accepted_inputs": {"text": True, "image": True, "audio": True, "file": False, "video": False}},
        "context": {"scenario_context": "tp_should_not_be_recorded"},
        "generation_options": {"generate_images": True, "generate_audio": True},
        "test_config": {"num_variations": 3},
    }

    plan = api_probe.build_api_probe_batch_plan(
        target_operation="create-request",
        request=request,
        allow_media_generation=True,
        allow_non_text_inputs=True,
        max_request_variations=3,
        small_batch_size=1,
    )

    assert plan["phase_order"] == ["dry-run", "small-batch", "batch"]
    assert plan["small_batch_size"] == 1
    assert plan["batch_size"] == 3
    assert [item["modality"] for item in plan["modality_sequence"]] == ["text", "image", "audio"]
    assert plan["phases"][0]["estimated_real_api_calls"] == 0
    assert plan["phases"][1]["phase"] == "small-batch"
    assert plan["phases"][1]["modalities"] == ["text"]
    assert plan["phases"][2]["modalities"] == ["text", "image", "audio"]
    assert plan["guardrails"]["media_after_text_small_batch"] is True
    assert plan["guardrails"]["sensitive_values_not_recorded"] is True
    assert plan["quota_stop_go"]["decision"] == "wait"
    assert plan["quota_stop_go"]["source"] == "not-provided"
    assert plan["quota_stop_go"]["can_enter_small_batch"] is False
    assert "tp_should_not_be_recorded" not in json.dumps(plan)


def test_api_probe_batch_plan_quota_record_stops_until_reset():
    quota_record = {
        "status": "error",
        "response_headers": {"retry-after": "60", "x-ratelimit-reset": "2026-07-06T01:00:00Z"},
        "error": {
            "response": {
                "message": "Usage limit exceeded for requests",
                "quota": {"resource": "requests", "limit": 5, "used": 5, "requested": 1, "remaining": 0},
            }
        },
    }

    plan = api_probe.build_api_probe_batch_plan(target_operation="create-request", request={"agent": {"accepted_inputs": {"text": True}}, "test_config": {"num_variations": 1}}, quota_record=quota_record)

    quota_gate = plan["quota_stop_go"]
    assert quota_gate["decision"] == "stop"
    assert quota_gate["can_enter_small_batch"] is False
    assert quota_gate["can_enter_batch"] is False
    assert quota_gate["quota"]["blocked"] is True
    assert quota_gate["quota"]["resource"] == "requests"
    assert quota_gate["reset"]["known"] is True
    assert quota_gate["reset"]["retry_after_seconds"] == 60
    assert quota_gate["reset"]["ratelimit_reset"] == "2026-07-06T01:00:00Z"


def test_api_probe_batch_plan_requires_quota_evidence_for_go():
    plan = api_probe.build_api_probe_batch_plan(target_operation="create-request", request={"agent": {"accepted_inputs": {"text": True}}, "test_config": {"num_variations": 1}})

    quota_gate = plan["quota_stop_go"]
    assert quota_gate["decision"] == "wait"
    assert quota_gate["source"] == "not-provided"
    assert quota_gate["evidence_present"] is False
    assert quota_gate["quota_or_reset_evidence_present"] is False
    assert quota_gate["can_enter_small_batch"] is False


def test_api_probe_plan_batch_cli_does_not_create_api_client(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    output = tmp_path / "plan.json"
    request_file.write_text(json.dumps({"agent": {"accepted_inputs": {"text": True}}, "test_config": {"num_variations": 2}}), encoding="utf-8")

    def fail_from_env(cls, **_kwargs):
        raise AssertionError("plan-batch should not construct an API client")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(fail_from_env))

    code = api_probe.main(["plan-batch", "--request-file", str(request_file), "--output", str(output)])
    captured = capsys.readouterr()

    assert code == 0
    assert "planned plan-batch" in captured.out
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["function"] == "plan_batch"
    assert record["status"] == "blocked"
    assert record["response"]["plan"]["batch_size"] == 2


def test_api_probe_validate_gate_cli_accepts_fresh_target_bound_gate(tmp_path, capsys):
    gate_file = tmp_path / "gate.json"
    output = tmp_path / "validation.json"
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", target_operation="create-request")), encoding="utf-8")

    code = api_probe.main(["validate-gate", "--target-operation", "create-request", "--quota-gate-record", str(gate_file), "--output", str(output), "--allow-nonprivate-output"])
    captured = capsys.readouterr()
    record = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert "validated validate-gate: status=ok issues=0" in captured.out
    assert record["schema_version"] == api_probe.API_PROBE_GATE_VALIDATION_SCHEMA_VERSION
    assert record["response"]["validation"]["valid"] is True
    assert record["response"]["validation"]["target_operation"] == "create-request"


def test_api_probe_quota_gate_schema_snapshot_matches_validator_contract():
    schema = json.loads((Path(__file__).resolve().parents[2] / "docs" / "a1" / "schemas" / "api_probe_quota_gate.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["schema_version"]["const"] == api_probe.API_PROBE_BATCH_PLAN_SCHEMA_VERSION
    assert schema["properties"]["function"]["const"] == "plan_batch"
    plan_schema = schema["properties"]["response"]["properties"]["plan"]
    assert {"schema_version", "target_operation", "created_at", "target_binding", "quota_stop_go"}.issubset(plan_schema["required"])
    binding_schema = plan_schema["properties"]["target_binding"]
    assert binding_schema["properties"]["schema_version"]["const"] == api_probe.API_PROBE_TARGET_BINDING_SCHEMA_VERSION
    assert {"fingerprint", "request_fingerprint", "raw_request_not_recorded"}.issubset(binding_schema["required"])
    gate_schema = plan_schema["properties"]["quota_stop_go"]
    assert gate_schema["properties"]["decision"]["enum"] == ["go", "stop", "wait"]


def test_api_probe_validate_gate_cli_rejects_wrong_target(tmp_path, capsys):
    gate_file = tmp_path / "gate.json"
    output = tmp_path / "validation.json"
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", target_operation="create-run")), encoding="utf-8")

    code = api_probe.main(["validate-gate", "--target-operation", "create-request", "--quota-gate-record", str(gate_file), "--output", str(output), "--allow-nonprivate-output"])
    captured = capsys.readouterr()
    record = json.loads(output.read_text(encoding="utf-8"))

    assert code == 2
    assert "target_operation" in captured.err
    assert record["status"] == "error"
    assert record["response"]["validation"]["issues"][0]["code"] == "target_operation_mismatch"


def test_api_probe_validate_gate_cli_rejects_stale_gate(tmp_path, capsys):
    gate_file = tmp_path / "gate.json"
    output = tmp_path / "validation.json"
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", created_at="2026-01-01T00:00:00Z")), encoding="utf-8")

    code = api_probe.main(["validate-gate", "--target-operation", "create-request", "--quota-gate-record", str(gate_file), "--quota-gate-ttl-seconds", "1", "--output", str(output), "--allow-nonprivate-output"])
    captured = capsys.readouterr()
    record = json.loads(output.read_text(encoding="utf-8"))

    assert code == 2
    assert "stale" in captured.err
    assert record["response"]["validation"]["issues"][0]["code"] == "stale_gate"


def test_api_probe_validate_gate_cli_rejects_same_operation_wrong_request_binding(tmp_path, capsys):
    original_request = {"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}
    changed_request = {"agent": {"name": "Changed"}, "test_config": {"num_variations": 1}}
    gate_file = tmp_path / "gate.json"
    request_file = tmp_path / "changed_request.json"
    output = tmp_path / "validation.json"
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", request=original_request)), encoding="utf-8")
    request_file.write_text(json.dumps(changed_request), encoding="utf-8")

    code = api_probe.main(["validate-gate", "--target-operation", "create-request", "--request-file", str(request_file), "--quota-gate-record", str(gate_file), "--output", str(output), "--allow-nonprivate-output"])
    captured = capsys.readouterr()
    record = json.loads(output.read_text(encoding="utf-8"))

    assert code == 2
    assert "target_binding.fingerprint" in captured.err
    assert record["response"]["validation"]["issues"][0]["code"] == "target_binding_mismatch"


def test_api_probe_protected_output_requires_private_dir_before_key_lookup(tmp_path, capsys):
    output = tmp_path / "real.json"

    code = api_probe.main(["health-check", "--execute", "--output", str(output)])
    captured = capsys.readouterr()

    assert code == 2
    assert "docs/evidence/private_refs" in captured.err
    assert "RELEASEFOUNDRY_API_KEY" not in captured.err
    assert not output.exists()


def test_api_probe_validate_gate_protected_output_blocks_before_gate_read(tmp_path, capsys):
    output = tmp_path / "validation.json"
    missing_gate = tmp_path / "missing-gate.json"

    code = api_probe.main(["validate-gate", "--quota-gate-record", str(missing_gate), "--output", str(output)])
    captured = capsys.readouterr()

    assert code == 2
    assert "docs/evidence/private_refs" in captured.err
    assert "quota-gate-record" not in captured.err
    assert not output.exists()


def test_api_probe_quota_record_protected_output_blocks_before_record_read(tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    output = tmp_path / "plan.json"
    missing_quota = tmp_path / "missing-quota.json"

    code = api_probe.main(["plan-batch", "--request-file", str(request_file), "--quota-record", str(missing_quota), "--output", str(output)])
    captured = capsys.readouterr()

    assert code == 2
    assert "docs/evidence/private_refs" in captured.err
    assert "quota-record" not in captured.err
    assert not output.exists()


def test_api_probe_output_policy_marks_synthetic_override(tmp_path, capsys):
    gate_file = tmp_path / "gate.json"
    output = tmp_path / "validation.json"
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", target_operation="create-request")), encoding="utf-8")

    code = api_probe.main(["validate-gate", "--target-operation", "create-request", "--quota-gate-record", str(gate_file), "--output", str(output), "--allow-nonprivate-output"])
    capsys.readouterr()
    record = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert record["output_policy"]["private_output_required"] is True
    assert record["output_policy"]["allow_nonprivate_output"] is True
    assert record["output_policy"]["nonprivate_output_override_used"] is True
    assert record["output_policy"]["sink"] == "nonprivate_file"


def test_api_probe_read_only_parity_operations_dry_run_without_key(tmp_path):
    root = Path(__file__).resolve().parents[2]
    operations = {
        "health-check": "keep_alive",
        "list-agents": "list_agents",
    }

    for operation, expected_function in operations.items():
        output = tmp_path / f"{operation}.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "services.runner.api_probe",
                operation,
                "--output",
                str(output),
            ],
            cwd=str(root),
            text=True,
            capture_output=True,
            check=False,
        )

        assert completed.returncode == 0
        record = json.loads(output.read_text(encoding="utf-8"))
        assert record["status"] == "planned"
        assert record["attempts"] == 0
        assert record["request"]["function"] == expected_function
        assert record["request"]["mutates"] is False
        assert record["output_policy"]["schema_version"] == "releasefoundry.output_policy.v1"
        assert record["output_policy"]["private_output_required"] is False
        assert record["output_policy"]["sink"] == "nonprivate_file"


def test_api_probe_create_request_schema_file_marks_source_and_sends_schema(tmp_path):
    request_file = tmp_path / "request.json"
    schema_file = tmp_path / "schema.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    schema_file.write_text(json.dumps(schema), encoding="utf-8")

    class FakeClient:
        def create_request(self, **kwargs):
            return {
                "request_schema": kwargs["request_input_schema"],
                "allow_media_generation": kwargs["allow_media_generation"],
                "allow_non_text_inputs": kwargs["allow_non_text_inputs"],
                "max_request_variations": kwargs["max_request_variations"],
            }

    record = api_probe.run_operation(
        FakeClient(),
        Namespace(
            operation="create-request",
            request_name="Schema file",
            request_file=str(request_file),
            request_schema_file=str(schema_file),
            allow_media_generation=False,
            allow_non_text_inputs=False,
            max_request_variations=1,
        ),
        output=tmp_path / "probe.json",
        dry_run=True,
    )

    assert record["request_schema"] == schema
    assert record["allow_media_generation"] is False
    assert record["allow_non_text_inputs"] is False
    assert record["max_request_variations"] == 1


def test_api_probe_create_request_preflight_blocks_media_generation():
    preflight = api_probe.summarize_generation_request(
        {
            "generation_options": {"generate_audio": True},
            "test_config": {"num_variations": 1},
        }
    )

    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "--allow-media-generation" in str(exc)
    else:
        raise AssertionError("expected media generation guardrail to block execution")


def test_api_probe_create_request_preflight_blocks_large_variation_count():
    preflight = api_probe.summarize_generation_request(
        {
            "generation_options": {"generate_audio": False},
            "test_config": {"num_variations": 3},
        }
    )

    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "num_variations=3" in str(exc)
    else:
        raise AssertionError("expected variation guardrail to block execution")


def test_api_probe_create_request_preflight_blocks_unknown_variation_count():
    preflight = api_probe.summarize_generation_request(
        {
            "generation_options": {"generate_audio": False},
            "test_config": {},
        }
    )

    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "num_variations is unknown" in str(exc)
    else:
        raise AssertionError("expected unknown variation guardrail to block execution")


def test_api_probe_create_request_preflight_blocks_invalid_variation_shapes():
    for value in (0, False, True, 1.5, "1.5"):
        preflight = api_probe.summarize_generation_request({"generation_options": {}, "test_config": {"num_variations": value}})
        assert preflight["num_variations"] is None
        assert preflight["num_variations_known"] is False
        try:
            api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
        except ValueError as exc:
            assert "num_variations is unknown" in str(exc)
        else:
            raise AssertionError(f"expected invalid variation {value!r} to block execution")


def test_api_probe_create_request_preflight_blocks_non_text_inputs():
    preflight = api_probe.summarize_generation_request(
        {
            "agent": {"accepted_inputs": {"text": True, "audio": True}},
            "generation_options": {"generate_audio": False},
            "test_config": {"num_variations": 1},
        }
    )

    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "--allow-non-text-inputs" in str(exc)
    else:
        raise AssertionError("expected non-text input guardrail to block execution")


def test_api_probe_create_request_preflight_supports_enabled_dict_inputs():
    preflight = api_probe.summarize_generation_request(
        {
            "agent": {"accepted_inputs": {"text": {"enabled": True}, "image": {"enabled": False}}},
            "generation_options": {"generate_audio": False},
            "test_config": {"num_variations": "1"},
        }
    )

    assert preflight["accepted_inputs_known"] is True
    assert preflight["accepted_input_flags"]["text"] is True
    assert preflight["accepted_input_flags"]["image"] is False
    assert preflight["num_variations"] == 1
    assert preflight["cost_risk"]["level"] == "text_small_batch"
    api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)


def test_create_request_preflight_cost_risk_marks_paid_media_and_batches():
    preflight = summarize_generation_request(
        {
            "agent": {"accepted_inputs": {"text": True, "audio": True, "file": True}},
            "generation_options": {"generate_audio": True, "generate_files": True},
            "test_config": {"num_variations": 3},
        }
    )

    assert preflight["cost_risk"]["level"] == "paid_media_generation"
    assert preflight["cost_risk"]["estimated_generated_asset_units"] == 6
    assert preflight["cost_risk"]["generated_media_modalities"] == ["audio", "files"]
    assert preflight["cost_risk"]["non_text_input_modalities"] == ["audio", "file"]
    assert "multi_variation_batch" in preflight["cost_risk"]["reasons"]


def test_api_probe_create_request_preflight_blocks_unsupported_accepted_inputs_shape():
    preflight = api_probe.summarize_generation_request(
        {
            "agent": {"accepted_inputs": ["image"]},
            "generation_options": {},
            "test_config": {"num_variations": 1},
        }
    )

    assert preflight["accepted_inputs_known"] is False
    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "accepted_inputs shape is unsupported" in str(exc)
    else:
        raise AssertionError("expected unsupported accepted_inputs shape to block execution")


def test_api_probe_create_request_preflight_blocks_each_non_text_input():
    for input_name in ("audio", "file", "image", "video", "conversation"):
        preflight = api_probe.summarize_generation_request(
            {
                "agent": {"accepted_inputs": {"text": True, input_name: True}},
                "generation_options": {},
                "test_config": {"num_variations": 1},
            }
        )

        assert preflight["accepted_input_flags"][input_name] is True
        try:
            api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
        except ValueError as exc:
            assert "--allow-non-text-inputs" in str(exc)
        else:
            raise AssertionError(f"expected {input_name} input guardrail to block execution")


def test_api_probe_create_request_preflight_blocks_each_media_generation_flag():
    cases = {
        "generate_audio": "audio",
        "generate_files": "files",
        "generate_images": "images",
        "generate_videos": "videos",
        "generate_simulations": "simulations",
    }
    for raw_flag, normalized_flag in cases.items():
        preflight = api_probe.summarize_generation_request(
            {
                "generation_options": {raw_flag: True},
                "test_config": {"num_variations": 1},
            }
        )

        assert preflight["media_generation"][normalized_flag] is True
        try:
            api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
        except ValueError as exc:
            assert "--allow-media-generation" in str(exc)
        else:
            raise AssertionError(f"expected {raw_flag} generation guardrail to block execution")


def test_media_interface_fixture_is_dry_run_only_guarded():
    fixture = json.loads((Path(__file__).resolve().parents[2] / "docs" / "a1" / "api_calibration" / "media_interface_request.json").read_text(encoding="utf-8"))
    preflight = api_probe.summarize_generation_request(fixture)

    assert preflight["media_generation"]["images"] is True
    assert preflight["media_generation"]["audio"] is True
    assert preflight["media_generation"]["files"] is True
    assert preflight["accepted_input_flags"]["image"] is True
    assert preflight["accepted_input_flags"]["audio"] is True
    assert preflight["accepted_input_flags"]["file"] is True
    assert preflight["agent_input_schema_version"] == "releasefoundry.agent_input.v1"
    assert preflight["media_generation"]["videos"] is True
    assert preflight["accepted_input_flags"]["video"] is True
    assert preflight["agent_input_part_types"] == ["text", "image", "audio", "file", "video"]
    try:
        api_probe.enforce_create_request_preflight(preflight, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=1)
    except ValueError as exc:
        assert "--allow-media-generation" in str(exc)
    else:
        raise AssertionError("expected media fixture to be blocked without explicit media allowance")


def test_media_interface_fixture_dry_run_records_agent_input_schema_shape(tmp_path):
    fixture = json.loads((Path(__file__).resolve().parents[2] / "docs" / "a1" / "api_calibration" / "media_interface_request.json").read_text(encoding="utf-8"))
    output = tmp_path / "media_probe.json"
    client = ReleaseFoundryApiClient(**{"api_" + "key": None})

    record = client.create_request(
        request_name="A1 Media Interface Dry Run",
        request=fixture,
        output_path=output,
        dry_run=True,
        preflight=api_probe.summarize_generation_request(fixture),
    )

    schema_summary = record["request"]["params"]["request_input_schema"]
    assert schema_summary["agent_input_schema_version"] == "releasefoundry.agent_input.v1"
    assert schema_summary["agent_input_part_types"] == ["audio", "file", "image", "text", "video"]
    assert schema_summary["property_keys"] == ["metadata", "parts", "schema_version", "text"]
    assert schema_summary["defs_keys"] == ["agent_input_part"]
    assert json.loads(output.read_text(encoding="utf-8"))["request"]["params"]["request_input_schema"] == schema_summary


def test_redact_sensitive_handles_nested_values():
    payload = {
        "Authorization": "Bearer tp_secret",
        "api_key": "tp_secret",
        "key": "tp_secret",
        "nested": [{"password": "pw", "safe": "ok"}],
    }

    assert redact_sensitive(payload) == {
        "Authorization": "[redacted]",
        "api_key": "[redacted]",
        "key": "[redacted]",
        "nested": [{"password": "[redacted]", "safe": "ok"}],
    }


def test_redact_text_covers_token_key_bearer_and_email():
    text = "token tp_secret123 sk-testtesttest Bearer abc.def-123 user@example.com"

    assert redact_text(text) == "token [redacted] [redacted] [redacted] [redacted]"


def test_api_probe_cli_defaults_to_dry_run_without_env(tmp_path):
    output = tmp_path / "probe.json"
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "services.runner.api_probe", "init", "--output", str(output)],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "planned init" in completed.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "planned"


def test_api_probe_cli_requires_allow_mutate_for_execute(tmp_path):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "context": {"domain": "tests"}}), encoding="utf-8")
    env = os.environ.copy()
    env.pop("RELEASEFOUNDRY_API_KEY", None)
    env.pop("RELEASEFOUNDRY_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, "-B", "-m", "services.runner.api_probe", "create-request", "--execute", "--request-name", "Blocked", "--request-file", str(request_file)],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 2
    assert "--allow-mutate" in completed.stderr
    assert "RELEASEFOUNDRY_API_KEY" not in completed.stderr


def test_api_probe_cli_create_request_execute_requires_zero_retries_before_env(tmp_path):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    env = os.environ.copy()
    env.pop("RELEASEFOUNDRY_API_KEY", None)
    env.pop("RELEASEFOUNDRY_API_KEY", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.runner.api_probe",
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "1",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 2
    assert "--max-retries 0" in completed.stderr
    assert "RELEASEFOUNDRY_API_KEY" not in completed.stderr


def test_api_probe_cli_mutating_execute_requires_quota_gate_before_env(tmp_path):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    env = os.environ.copy()
    env.pop("RELEASEFOUNDRY_API_KEY", None)
    env.pop("RELEASEFOUNDRY_API_KEY", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.runner.api_probe",
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 2
    assert "--quota-gate-record" in completed.stderr
    assert "RELEASEFOUNDRY_API_KEY" not in completed.stderr


def test_api_probe_cli_mutating_execute_blocks_stop_quota_gate(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "quota_stop.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(json.dumps(probe_plan_gate_payload("stop")), encoding="utf-8")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "quota gate decision=stop" in captured.err


def test_api_probe_cli_mutating_execute_rejects_read_only_quota_gate(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "list_requests.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(
        json.dumps(
            {
                "function": "list_requests",
                "dry_run": False,
                "status": "ok",
                "response": {"status": "ok", "requests": []},
                "field_map_version": api_probe.RELEASEFOUNDRY_API_FIELD_MAP_VERSION,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "plan-batch record" in captured.err


def test_api_probe_cli_mutating_execute_rejects_go_gate_without_evidence(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "go_without_evidence.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(
        json.dumps(
            {
                "schema_version": api_probe.API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
                "function": "plan_batch",
                "response": {"plan": {"schema_version": api_probe.API_PROBE_BATCH_PLAN_SCHEMA_VERSION, "target_operation": "create-request", "created_at": api_probe.utc_now(), "quota_stop_go": {"decision": "go", "source": "not-provided"}}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "requires reviewed quota/reset evidence" in captured.err


def test_api_probe_cli_mutating_execute_rejects_wrong_target_gate_before_env(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "wrong_target.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", target_operation="create-run")), encoding="utf-8")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "target_operation" in captured.err


def test_api_probe_cli_mutating_execute_rejects_stale_gate_before_env(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "stale_gate.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", created_at="2026-01-01T00:00:00Z")), encoding="utf-8")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
            "--quota-gate-ttl-seconds",
            "1",
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "stale" in captured.err


def test_api_probe_cli_mutating_execute_rejects_wrong_request_binding_before_env(monkeypatch, tmp_path, capsys):
    original_request = {"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}
    changed_request = {"agent": {"name": "Changed"}, "test_config": {"num_variations": 1}}
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "wrong_request_binding.json"
    request_file.write_text(json.dumps(changed_request), encoding="utf-8")
    gate_file.write_text(json.dumps(probe_plan_gate_payload("go", request=original_request)), encoding="utf-8")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: (_ for _ in ()).throw(AssertionError("client should not be constructed"))))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "target_binding.fingerprint" in captured.err


def test_api_probe_cli_mutating_execute_allows_audited_quota_override(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    gate_file = tmp_path / "quota_stop.json"
    output_file = tmp_path / "override.json"
    request_file.write_text(json.dumps({"agent": {"name": "Mock"}, "test_config": {"num_variations": 1}}), encoding="utf-8")
    gate_file.write_text(json.dumps(probe_plan_gate_payload("stop")), encoding="utf-8")

    class FakeClient:
        def create_request(self, **kwargs):
            assert kwargs["dry_run"] is False
            record = {
                "function": "create_request",
                "dry_run": False,
                "status": "ok",
                "attempts": 1,
                "request": {"preflight": {}},
                "field_map_version": api_probe.RELEASEFOUNDRY_API_FIELD_MAP_VERSION,
            }
            api_probe.write_json(kwargs["output_path"], record)
            return record

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: FakeClient()))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Override",
            "--request-file",
            str(request_file),
            "--quota-gate-record",
            str(gate_file),
            "--allow-quota-override",
            "--quota-override-reason",
            "manual paid calibration approved after external quota review",
            "--output",
            str(output_file),
            "--allow-nonprivate-output",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "executed create-request: status=ok" in captured.out
    record = json.loads(output_file.read_text(encoding="utf-8"))
    assert record["quota_gate"]["decision"] == "stop"
    assert record["quota_gate"]["override"]["used"] is True
    assert record["request"]["preflight"]["quota_gate"]["override"]["reason"] == "manual paid calibration approved after external quota review"


def test_api_probe_cli_execute_guardrails_block_before_client_call(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "agent": {"name": "Mock", "accepted_inputs": {"text": True, "image": True}},
                "generation_options": {"generate_images": True},
                "test_config": {"num_variations": 2},
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def create_request(self, **_kwargs):
            raise AssertionError("create_request should be blocked before client call")

    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: FakeClient()))

    code = api_probe.main(
        [
            "create-request",
            "--execute",
            "--allow-mutate",
            "--max-retries",
            "0",
            "--request-name",
            "Blocked",
            "--request-file",
            str(request_file),
            "--allow-quota-override",
            "--quota-override-reason",
            "unit test reaches media preflight guardrail",
            "--output",
            str(tmp_path / "blocked.json"),
            "--allow-nonprivate-output",
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "--allow-media-generation" in captured.err
    assert not (tmp_path / "blocked.json").exists()


def test_api_probe_cli_reports_timeout_without_traceback(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(api_probe.ReleaseFoundryApiClient, "from_env", classmethod(lambda cls, **_kwargs: object()))

    def raise_timeout(*_args, **_kwargs):
        raise TimeoutError("get_run did not complete within 1s")

    monkeypatch.setattr(api_probe, "run_operation", raise_timeout)

    code = api_probe.main(["poll-run", "--execute", "--run-id", "123", "--output", str(tmp_path / "poll.json"), "--allow-nonprivate-output"])
    captured = capsys.readouterr()

    assert code == 2
    assert "api probe error: get_run did not complete within 1s" in captured.err
    assert "Traceback" not in captured.err
