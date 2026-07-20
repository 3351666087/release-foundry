from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from browser_session_parity import check_outputs


ROOT = Path(__file__).resolve().parents[2]
PARITY_PATH = ROOT / "tests/a1/fixtures/browser_session_sdk_parity.json"


def test_generated_browser_session_parity_artifacts_are_current() -> None:
    assert check_outputs() == []


def test_parity_check_cli_is_executable() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "tests/a1/browser_session_parity.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "artifacts are current" in completed.stdout


def test_generated_go_capability_gate_is_truthful_and_public_safe() -> None:
    artifact = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
    assert artifact["public_safe"] is True
    assert artifact["contains_credential_values"] is False
    assert artifact["go"]["executable_operations"] == ["complete_login", "refresh"]
    assert artifact["go"]["unsupported_operations"] == [
        "bootstrap",
        "logout",
        "revoke_all",
    ]
    assert artifact["go"]["refresh_response_fields"] == ["schema_version", "status"]
    assert artifact["go"]["security_invariants"] == {
        "https_required": True,
        "same_origin_required": True,
        "idempotency_header_required": True,
        "refresh_reuse_clears_cookies": True,
        "cookie_values_absent_from_public_response": True,
    }
    serialized = json.dumps(artifact, sort_keys=True)
    assert "ashr_live_" not in serialized
    assert "Bearer " not in serialized
