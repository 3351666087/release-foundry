import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from ashr_clone.api_client import AshrApiClient, AshrApiError, redact_sensitive, redact_text  # noqa: E402
from services.runner import api_probe  # noqa: E402


def test_dry_run_records_plan_without_api_key(tmp_path):
    output = tmp_path / "dry_run.json"
    client = AshrApiClient(api_key=None)

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
    client = AshrApiClient(api_key="tp_test_secret", transport=transport, timeout=7)

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


def test_from_env_accepts_official_ashr_labs_names(monkeypatch):
    monkeypatch.delenv("ASHR_API_KEY", raising=False)
    monkeypatch.setenv("ASHR_LABS_API_KEY", "tp_labs_secret")
    monkeypatch.setenv("ASHR_LABS_BASE_URL", "https://example.invalid/ashr")

    client = AshrApiClient.from_env()

    assert repr(client) == "AshrApiClient(base_url='https://example.invalid/ashr', api_key=set)"


def test_retryable_status_retries_then_succeeds():
    calls = []

    def transport(_url, _headers, _body, _timeout):
        calls.append("call")
        if len(calls) == 1:
            return 429, b'{"status":"error","message":"rate limited"}'
        return 200, b'{"status":"ok","user":{"id":1},"tenant":{"id":2}}'

    client = AshrApiClient(api_key="tp_test_secret", transport=transport, max_retries=2, retry_backoff_seconds=0)

    record = client.init(dry_run=False)

    assert record["attempts"] == 2
    assert record["status_code"] == 200


def test_non_retryable_status_writes_error_record(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 401, b'{"status":"error","message":"bad key","api_key":"tp_secret"}'

    output = tmp_path / "error.json"
    client = AshrApiClient(api_key="tp_test_secret", transport=transport, max_retries=3)

    try:
        client.init(output_path=output, dry_run=False)
    except AshrApiError as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected AshrApiError")

    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["attempts"] == 1
    assert record["status"] == "error"
    assert record["error"]["response"]["api_key"] == "[redacted]"
    assert record["error"]["error_kind"] == "http"


def test_api_error_with_status_ok_has_api_error_kind(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"error","message":"dataset not found"}'

    output = tmp_path / "api_error.json"
    client = AshrApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.get_dataset(0, output_path=output, dry_run=False)
    except AshrApiError as exc:
        assert exc.status_code == 200
        assert exc.error_kind == "api"
    else:
        raise AssertionError("expected AshrApiError")

    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["status_code"] == 200
    assert record["error"]["error_kind"] == "api"


def test_error_message_text_is_redacted_in_file_and_exception(tmp_path):
    def transport(_url, _headers, _body, _timeout):
        return 200, b'{"status":"error","message":"bad key tp_leaked_secret for owner@example.com"}'

    output = tmp_path / "api_error.json"
    client = AshrApiClient(api_key="tp_test_secret", transport=transport, max_retries=0)

    try:
        client.get_dataset(0, output_path=output, dry_run=False)
    except AshrApiError as exc:
        assert "tp_leaked_secret" not in str(exc)
        assert "owner@example.com" not in str(exc)
        assert "[redacted]" in str(exc)
    else:
        raise AssertionError("expected AshrApiError")

    text = output.read_text(encoding="utf-8")
    assert "tp_leaked_secret" not in text
    assert "owner@example.com" not in text
    assert "[redacted]" in text


def test_poll_run_dry_run_records_estimated_calls(tmp_path):
    output = tmp_path / "poll_run.json"
    client = AshrApiClient(api_key=None)

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
    client = AshrApiClient(api_key="tp_test_secret", transport=transport)

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
    client = AshrApiClient(api_key="tp_test_secret", transport=transport)

    record = client.poll_request(request_id=7, timeout_seconds=1, poll_interval_seconds=0, output_path=output, dry_run=False)

    assert record["status"] == "ok"
    assert record["attempts"] == 2
    assert calls[0]["function"] == "get_request"
    assert json.loads(output.read_text(encoding="utf-8"))["response"]["request"]["request_status"] == "completed"


def test_create_request_dry_run_records_mutating_plan(tmp_path):
    output = tmp_path / "create_request.json"
    client = AshrApiClient(api_key=None)

    record = client.create_request(request_name="Tiny calibration", request={"agent": {"name": "Mock"}, "context": {"domain": "tests"}}, output_path=output, dry_run=True)

    assert record["status"] == "planned"
    assert record["request"]["function"] == "create_request"
    assert record["request"]["mutates"] is True
    assert record["request"]["params"]["request_name"] == "Tiny calibration"


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


def test_redact_text_covers_token_bearer_and_email():
    text = "token tp_secret123 Bearer abc.def-123 user@example.com"

    assert redact_text(text) == "token [redacted] [redacted] [redacted]"


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
    env.pop("ASHR_API_KEY", None)
    env.pop("ASHR_LABS_API_KEY", None)

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
    assert "ASHR_API_KEY" not in completed.stderr


def test_api_probe_cli_reports_timeout_without_traceback(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(api_probe.AshrApiClient, "from_env", classmethod(lambda cls, **_kwargs: object()))

    def raise_timeout(*_args, **_kwargs):
        raise TimeoutError("get_run did not complete within 1s")

    monkeypatch.setattr(api_probe, "run_operation", raise_timeout)

    code = api_probe.main(["poll-run", "--execute", "--run-id", "123", "--output", str(tmp_path / "poll.json")])
    captured = capsys.readouterr()

    assert code == 2
    assert "api probe error: get_run did not complete within 1s" in captured.err
    assert "Traceback" not in captured.err
