from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "fixtures" / "a2" / "sdk_surface" / "releasefoundry"
PACKAGE_ROOT = ROOT / "packages" / "sdk" / "releasefoundry"
OUTPUT = (
    ROOT
    / "docs"
    / "a1"
    / "_pypi_artifacts"
    / "releasefoundry-0.3.1-py3-none-any.whl"
)
DIST_INFO = "releasefoundry-0.3.1.dist-info"
ZIP_TIMESTAMP = (2026, 8, 2, 0, 0, 0)


def build() -> Path:
    entries = {
        "releasefoundry/__init__.py": (SOURCE_ROOT / "__init__.py").read_bytes(),
        "releasefoundry/client.py": (SOURCE_ROOT / "client.py").read_bytes(),
        "releasefoundry/eval.py": (SOURCE_ROOT / "eval.py").read_bytes(),
        "releasefoundry/run_builder.py": (PACKAGE_ROOT / "run_builder.py").read_bytes(),
        "releasefoundry/comparators.py": (PACKAGE_ROOT / "comparators.py").read_bytes(),
        f"{DIST_INFO}/METADATA": _metadata(),
        f"{DIST_INFO}/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Generator: releasefoundry-sdk-surface-fixture\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
        f"{DIST_INFO}/top_level.txt": b"releasefoundry\n",
    }
    record_name = f"{DIST_INFO}/RECORD"
    entries[record_name] = _record(entries, record_name)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, entries[name])
    return OUTPUT


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        "Name: releasefoundry\n"
        "Version: 0.3.1\n"
        "Summary: Static ReleaseFoundry SDK compatibility surface fixture\n"
        "License-Expression: Apache-2.0\n"
        "Requires-Python: >=3.10\n"
        "\n"
        "This artifact exists only for deterministic, offline interface auditing.\n"
    ).encode("utf-8")


def _record(entries: dict[str, bytes], record_name: str) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name in sorted(entries):
        digest = base64.urlsafe_b64encode(hashlib.sha256(entries[name]).digest()).rstrip(b"=")
        writer.writerow([name, "sha256=" + digest.decode("ascii"), len(entries[name])])
    writer.writerow([record_name, "", ""])
    return output.getvalue().encode("utf-8")


if __name__ == "__main__":
    print(build().relative_to(ROOT).as_posix())
