from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TS_PACKAGE = ROOT / "packages" / "ts" / "ashr-clone"


def test_round45_ts_contract_parity() -> None:
    completed = subprocess.run(
        ["node", "--test", "test/round45_ts_parity.test.mjs"],
        cwd=TS_PACKAGE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        "round45_ts Node contract test failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
