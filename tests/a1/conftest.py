import sys
from pathlib import Path


SDK_ROOT = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "docker: opt-in integration test that creates disposable Docker resources",
    )
