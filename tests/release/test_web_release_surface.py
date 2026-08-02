from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from services.product_release import (
    VERIFICATION_RECEIPT_SCHEMA,
    WEB_SURFACE_RECEIPT_ID,
    verify_web_production_surface,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_compliant_web_surface(root: Path) -> Path:
    web_root = root / "apps" / "webapp"
    (web_root / "app").mkdir(parents=True, exist_ok=True)
    (web_root / "components").mkdir(parents=True, exist_ok=True)
    (web_root / "app" / "globals.css").write_text(
        """
body { font-size: 16px; }
h1 { font-size: 44px; }
.eyebrow { font-size: 12px; }
nav { font-size: 14px; }
table, th, td { font-size: 14px; }
button {
  min-height: 44px;
  font-size: 15px;
}
input, select, textarea {
  min-height: 40px;
  font-size: 16px;
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (web_root / "components" / "page.tsx").write_text(
        'export function Page() { return <main><h1>真实企业控制台</h1></main>; }\n',
        encoding="utf-8",
    )
    return web_root


def test_compliant_production_surface_is_approved(tmp_path: Path) -> None:
    web_root = write_compliant_web_surface(tmp_path)

    result = verify_web_production_surface(web_root, repo_root=tmp_path)

    assert result["decision"] == "approve_web_surface"
    assert result["issue_count"] == 0
    assert result["scanned_file_count"] == 2


def test_typography_and_control_contract_fail_closed(tmp_path: Path) -> None:
    web_root = write_compliant_web_surface(tmp_path)
    (web_root / "app" / "globals.css").write_text(
        """
body { font-size: 14px; }
h1 { font-size: 24px; }
.eyebrow { font-size: 10px; }
nav { font-size: 12px; }
button { min-height: 32px; font-size: 11px; }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = verify_web_production_surface(web_root, repo_root=tmp_path)

    assert result["decision"] == "block_web_surface"
    assert "font_size_below_policy" in result["blocking_reasons"]
    assert "control_height_below_policy" in result["blocking_reasons"]
    messages = "\n".join(issue["message"] for issue in result["issues"])
    assert "body copy must be at least 16px" in messages
    assert "page and hero titles must be at least 28px" in messages
    assert "metadata and eyebrow text must be at least 12px" in messages
    assert "navigation, tables, and controls must be at least 14px" in messages


def test_mock_fixture_preview_and_not_implemented_source_is_blocked(
    tmp_path: Path,
) -> None:
    web_root = write_compliant_web_surface(tmp_path)
    (web_root / "components" / "page.tsx").write_text(
        """
export const source = "api-mock";
export const mode = "fixture";
export const run = run_fixture();
export const grade = grade_fixture();
export const backing = "fixture_backed";
export const api = "api_fixture";
export const entry = "进入只读预览";
export const pending = "暂未实现";
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = verify_web_production_surface(web_root, repo_root=tmp_path)

    assert result["decision"] == "block_web_surface"
    assert {
        "production_mock",
        "production_fixture",
        "read_only_preview",
        "not_implemented",
    }.issubset(set(result["blocking_reasons"]))


def test_invalid_utf8_and_mojibake_are_blocked(tmp_path: Path) -> None:
    web_root = write_compliant_web_surface(tmp_path)
    (web_root / "components" / "invalid.ts").write_bytes(b"export const x = '\xff';\n")
    (web_root / "components" / "mojibake.tsx").write_text(
        "export const label = '鐨勪袱濂?Release';\n",
        encoding="utf-8",
    )

    result = verify_web_production_surface(web_root, repo_root=tmp_path)

    assert result["decision"] == "block_web_surface"
    assert "invalid_utf8" in result["blocking_reasons"]
    assert "suspected_cjk_mojibake" in result["blocking_reasons"]
    assert "suspected_lossy_cjk_decode" in result["blocking_reasons"]


def test_cli_can_emit_product_release_receipt(tmp_path: Path) -> None:
    web_root = write_compliant_web_surface(tmp_path)
    receipt_path = tmp_path / "dist" / "receipts" / "web.production_surface.json"
    commit_sha = "a" * 40
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_web_release_surface.py"),
            "--web-root",
            str(web_root),
            "--repo-root",
            str(tmp_path),
            "--product-release-id",
            "releasefoundry-product@1.0.0",
            "--source-commit",
            commit_sha,
            "--receipt-output",
            str(receipt_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == VERIFICATION_RECEIPT_SCHEMA
    assert receipt["receipt_id"] == WEB_SURFACE_RECEIPT_ID
    assert receipt["product_release_id"] == "releasefoundry-product@1.0.0"
    assert receipt["source_commit"] == commit_sha
    assert receipt["mode"] == "live"
    assert receipt["status"] == "passed"
    assert receipt["exit_code"] == 0
    assert receipt["verification"]["decision"] == "approve_web_surface"
