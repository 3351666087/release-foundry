from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "a1_fresh_setup_smoke.py"


def test_fresh_setup_smoke_runs_outside_repo_without_pythonpath(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "-B", str(SMOKE_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary == {
        "max_workers": 4,
        "passed": 30,
        "pythonpath_required": False,
        "status": "passed",
        "total_cases": 30,
        "trace_completeness": 1.0,
    }
