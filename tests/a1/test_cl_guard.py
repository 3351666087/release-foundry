import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CL_GUARD_PATH = ROOT / "scripts" / "cl_guard.py"


def load_cl_guard():
    spec = importlib.util.spec_from_file_location("cl_guard", CL_GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cl_guard_commercial_anchors_pass_current_main_contracts():
    cl_guard = load_cl_guard()

    result = cl_guard.check_commercial_anchors()

    assert result["schema_version"] == "ashr.cl_guard.commercial.v1"
    assert result["status"] == "passed"
    assert result["blocker_count"] == 0
    assert result["checked_blocker_count"] >= 20
    assert result["commercial_summary"]["typescript_mainline"] is True
    assert result["commercial_summary"]["a1_a2_calibration_required"] is True
    assert result["commercial_summary"]["advisories_block_pr"] is False


def test_cl_guard_commercial_anchor_detects_missing_required_text():
    cl_guard = load_cl_guard()
    anchor = cl_guard.CommercialAnchor(
        "unit-missing-anchor",
        "README.md",
        ("definitely-not-present-commercial-anchor",),
        "A3",
        "Unit test anchor.",
    )

    finding = cl_guard.check_anchor(anchor)

    assert finding["anchor_id"] == "unit-missing-anchor"
    assert finding["issue"] == "missing_anchor_text"
    assert finding["missing"] == ["definitely-not-present-commercial-anchor"]


def test_cl_guard_plan_marks_a3_typescript_and_evidence_surfaces():
    cl_guard = load_cl_guard()

    plan = cl_guard.build_plan([
        "apps/dashboard/src/app.mjs",
        "packages/ts/ashr-clone/src/api-client.ts",
        "fixtures/a3/p3/a3_gate_cli_report.redacted.md",
    ]).to_json()

    assert plan["a3"] is True
    assert plan["typescript"] is True
    assert plan["evidence"] is True
    assert "apps/dashboard/src/app.mjs" in plan["reasons"]["a3"]
    assert "packages/ts/ashr-clone/src/api-client.ts" in plan["reasons"]["typescript"]
