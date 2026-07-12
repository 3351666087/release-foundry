from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SIDECAR = ROOT / "services" / "runner" / "rust-verifier-sidecar.sh"
WSL_DISTRIBUTION = os.environ.get("ASHR_WSL_DISTRIBUTION", "Ubuntu-24.04-Ashr")


def _wsl(*arguments: str) -> list[str]:
    return ["wsl.exe", "-d", WSL_DISTRIBUTION, "--", *arguments]


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        raise ValueError(f"expected an absolute Windows path: {resolved}")
    tail = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{tail}"


@pytest.mark.skipif(shutil.which("wsl.exe") is None, reason="WSL is required")
@pytest.mark.parametrize(
    ("mode", "expected_directory", "expected_code"),
    [
        ("success", "accepted", None),
        ("malformed", "rejected", "malformed_verifier_output"),
        ("nonzero", "rejected", "verification_failed"),
        ("timeout", "rejected", "verification_failed"),
    ],
)
def test_sidecar_fails_closed_and_binds_scope(tmp_path: Path, mode: str, expected_directory: str, expected_code: str | None) -> None:
    queue = tmp_path / "queue"
    objects = tmp_path / "objects"
    for directory in ("inbox", "bundles"):
        (queue / directory).mkdir(parents=True)
    (queue / "bundles" / "bundle.json").write_text("{}", encoding="utf-8")
    (queue / "inbox" / "job.json").write_text(
        json.dumps(
            {
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "run_id": "run-1",
                "bundle_file": "bundle.json",
            }
        ),
        encoding="utf-8",
    )
    verifier = tmp_path / "fake-verifier.sh"
    verifier.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$@" > "${ASHR_CAPTURE_ARGS}"
case "${ASHR_FAKE_MODE}" in
  success) printf '{"status":"ok","verification_level":"objects_verified","manifest_authenticated":true,"object_verification_performed":true,"schema_version":"v","algorithm":"hmac-sha256","key_id":"key","authenticated_bundle_digest":"%064d","evidence_digest":"%064d","evidence_items":1,"objects_verified":1,"total_size_bytes":2,"expires_at_unix_ms":3}\\n' 0 0 ;;
  malformed) printf '{' ;;
  nonzero) exit 7 ;;
  timeout) sleep 3 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    capture = tmp_path / "args.txt"
    command = [
        *_wsl(),
        "env",
        "ASHR_VERIFIER_KEY_ENV=ASHR_TEST_KEY",
        f"ASHR_VERIFIER_QUEUE_ROOT={_wsl_path(queue)}",
        f"ASHR_VERIFIER_OBJECT_ROOT={_wsl_path(objects)}",
        f"ASHR_VERIFIER_EXECUTABLE={_wsl_path(verifier)}",
        "ASHR_VERIFIER_TIMEOUT_SECONDS=1",
        "ASHR_VERIFIER_ONCE=1",
        f"ASHR_FAKE_MODE={mode}",
        f"ASHR_CAPTURE_ARGS={_wsl_path(capture)}",
        "sh",
        _wsl_path(SIDECAR),
    ]
    subprocess.run(_wsl("chmod", "+x", _wsl_path(verifier)), check=True)
    subprocess.run(command, check=True, timeout=10)

    assert (queue / expected_directory / "job.json").exists()
    result = json.loads((queue / expected_directory / "job.verification.json").read_text(encoding="utf-8"))
    if expected_code is None:
        assert result["status"] == "ok"
        arguments = capture.read_text(encoding="utf-8").splitlines()
        assert _flag(arguments, "--expected-tenant-digest") == hashlib.sha256(b"tenant-1").hexdigest()
        assert _flag(arguments, "--expected-project-digest") == hashlib.sha256(b"project-1").hexdigest()
        assert _flag(arguments, "--expected-bundle-id-digest") == hashlib.sha256(b"run-1").hexdigest()
    else:
        assert result == {"status": "rejected", "code": expected_code}


@pytest.mark.skipif(shutil.which("wsl.exe") is None, reason="WSL is required")
@pytest.mark.parametrize(
    "job",
    [
        {"tenant_id": "t", "project_id": "p", "run_id": "r"},
        {"tenant_id": "t", "project_id": "p", "run_id": "r", "bundle_file": "../escape.json"},
        {"tenant_id": "t", "project_id": "p", "run_id": "r", "bundle_file": "missing.json"},
    ],
)
def test_sidecar_rejects_malformed_and_escaping_jobs(tmp_path: Path, job: dict[str, str]) -> None:
    queue = tmp_path / "queue"
    (queue / "inbox").mkdir(parents=True)
    (queue / "bundles").mkdir()
    (queue / "inbox" / "job.json").write_text(json.dumps(job), encoding="utf-8")
    verifier = tmp_path / "unused.sh"
    verifier.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8", newline="\n")
    subprocess.run(_wsl("chmod", "+x", _wsl_path(verifier)), check=True)
    subprocess.run(
        [
            *_wsl(), "env", "ASHR_VERIFIER_KEY_ENV=ASHR_TEST_KEY",
            f"ASHR_VERIFIER_QUEUE_ROOT={_wsl_path(queue)}",
            f"ASHR_VERIFIER_OBJECT_ROOT={_wsl_path(tmp_path / 'objects')}",
            f"ASHR_VERIFIER_EXECUTABLE={_wsl_path(verifier)}",
            "ASHR_VERIFIER_ONCE=1", "sh", _wsl_path(SIDECAR),
        ],
        check=True,
    )
    result = json.loads((queue / "rejected" / "job.verification.json").read_text(encoding="utf-8"))
    assert result["status"] == "rejected"
    assert result["code"] in {"malformed_job", "invalid_bundle_path"}


def _flag(arguments: list[str], name: str) -> str:
    return arguments[arguments.index(name) + 1]
