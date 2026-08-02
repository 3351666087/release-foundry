import json

from services.report.a3_a1_sandbox_probe import main, run_probe


def test_a1_self_host_sandbox_probe_exercises_real_local_runtime_contracts():
    payload = run_probe(observed_at="2026-07-13T08:00:00.000Z")

    assert payload["schema_version"] == "a3.a1_self_host_sandbox_probe.v1"
    assert payload["status"] == "sandbox_verified"
    assert payload["summary"] == {
        "total_checks": 4,
        "passed": 4,
        "failed": 0,
        "production_gap_count": 5,
    }
    checks = {item["id"]: item for item in payload["checks"]}
    assert checks["a1_control_plane_health"]["observed"] == {
        "http_status": 200,
        "service": "releasefoundry-saas-control-plane",
        "service_status": "ok",
        "local_only": True,
        "external_api_used": False,
    }
    assert checks["a1_worker_retry_dead_letter"]["observed"]["state_sequence"] == [
        "queued",
        "leased",
        "retrying",
        "dead_lettered",
    ]
    assert checks["a1_worker_expired_lease_recovery"]["observed"]["expired_lease_recovered"] is True
    assert checks["a1_local_object_storage_integrity"]["observed"]["write_readback_verified"] is True
    assert checks["a1_local_object_storage_integrity"]["observed"]["tamper_detected"] is True
    assert all(item["production_proof"] is False for item in payload["checks"])
    assert all(item["status"] == "not_run" for item in payload["production_gaps"])
    assert payload["authority_boundary"]["production_verified"] is False
    assert payload["authority_boundary"]["deployment_acceptance_mutated"] is False
    assert payload["authority_boundary"]["a2_decision_recomputed"] is False
    assert payload["safety"]["external_network_used"] is False
    assert payload["safety"]["releasefoundry_api_used"] is False


def test_a1_self_host_sandbox_probe_cli_emits_only_public_safe_json(capsys):
    assert main(["--observed-at", "2026-07-13T08:00:00.000Z"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["status"] == "sandbox_verified"
    assert "C:\\Users\\" not in serialized
    assert "/home/" not in serialized
    assert "Bearer " not in serialized
    assert "github_pat_" not in serialized
    assert "sk-" not in serialized
    assert "@" not in serialized
    assert captured.err == ""
