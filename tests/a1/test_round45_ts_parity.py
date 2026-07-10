from __future__ import annotations

import subprocess
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TS_PACKAGE = ROOT / "packages" / "ts" / "ashr-clone"


def test_round45_ts_contract_parity() -> None:
    npm = shutil.which("npm")
    assert npm is not None, "npm is required for the TypeScript parity contract"

    installed = subprocess.run(
        [npm, "ci"],
        cwd=TS_PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert installed.returncode == 0, (
        "round45_ts dependency install failed\n"
        f"stdout:\n{installed.stdout}\n"
        f"stderr:\n{installed.stderr}"
    )

    built = subprocess.run(
        [npm, "run", "build"],
        cwd=TS_PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert built.returncode == 0, (
        "round45_ts TypeScript build failed\n"
        f"stdout:\n{built.stdout}\n"
        f"stderr:\n{built.stderr}"
    )

    completed = subprocess.run(
        ["node", "--test", "test/round45_ts_parity.test.mjs"],
        cwd=TS_PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, (
        "round45_ts Node contract test failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
