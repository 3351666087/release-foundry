from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"


def test_sdk_builds_and_installs_into_isolated_virtualenv(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheel_dir), str(SDK_ROOT)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(wheel_dir.glob("ashr_clone_sdk-*.whl"))
    assert len(wheels) == 1

    environment = tmp_path / "consumer"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    isolated_env = os.environ.copy()
    isolated_env.pop("PYTHONPATH", None)
    isolated_env.pop("PYTHONHOME", None)
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import json, ashr_clone; "
                "from ashr_clone import AgentAdapter, SaaSIngestionClient, TraceRecorder; "
                "print(json.dumps({'module': ashr_clone.__name__, "
                "'exports': [x.__name__ for x in (AgentAdapter, SaaSIngestionClient, TraceRecorder)]}))"
            ),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env=isolated_env,
    )
    assert json.loads(probe.stdout) == {
        "module": "ashr_clone",
        "exports": ["AgentAdapter", "SaaSIngestionClient", "TraceRecorder"],
    }
