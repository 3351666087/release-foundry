#!/usr/bin/env python3
"""Selective CL gate for Ashr Codex Factory.

The gate is intentionally conservative where correctness matters and selective
where unrelated stacks would create noisy or expensive checks. It answers two
questions for CI:

1. Which test suites are relevant to this change list?
2. Are there high-confidence repository hygiene blockers that should stop a PR?

It avoids broad heuristic failures: docs-only changes do not run every language
suite, and the secret scanner only blocks on high-confidence token formats.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, NamedTuple

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIR_PREFIXES = (
    ".git/",
    ".secrets/",
    "docs/evidence/private_refs/",
    "node_modules/",
    "packages/ts/ashr-clone/node_modules/",
    "tmp/",
    "output/",
    "recon/",
)

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tgz",
    ".whl", ".woff", ".woff2", ".ttf", ".mp4", ".wav", ".bin", ".pyc",
}

# High-confidence patterns only. Broad "Bearer ..." scans are deliberately not
# included because tests and docs contain redacted/examples; false positives
# would train contributors to ignore the gate.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("github_legacy_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)

NON_SECRET_HINTS = (
    "redacted",
    "example",
    "example.invalid",
    "placeholder",
    "dummy",
    "fixture",
    "test-token",
    "local-demo",
)

PINNED_A3_ARTIFACT_PREFIXES = (
    "fixtures/a3/p3/a3_gate_cli_",
    "fixtures/a3/p3/a3_audit_bundle_",
    "fixtures/a3/p3/a3_audit_archive_",
)
PINNED_A3_ARTIFACT_SUFFIXES = (".json", ".md")


class CommercialAnchor(NamedTuple):
    anchor_id: str
    path: str
    contains: tuple[str, ...]
    lane: str
    purpose: str


COMMERCIAL_ANCHORS: tuple[CommercialAnchor, ...] = (
    CommercialAnchor(
        "strategy-agent-release-os",
        "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
        ("Agent Release OS", "TypeScript + React + Next.js", "Playwright", "Postgres"),
        "A1/A2/A3",
        "Keeps every CL tied to the commercial SaaS endgame instead of isolated demos.",
    ),
    CommercialAnchor(
        "cl-workflow-selective-matrix",
        ".github/workflows/cl-gate.yml",
        ("python-a1-a2", "a3-node", "typescript-sdk", "go-sdk", "evidence-gate"),
        "A1/A2/A3",
        "Ensures CI still routes A1, A2, A3, TypeScript, Go, and evidence checks.",
    ),
    CommercialAnchor(
        "dashboard-webapp-split",
        "apps/dashboard/index.html",
        ("./src/styles.css", "./src/app.mjs"),
        "A3",
        "Prevents regression back to a giant HTML blob.",
    ),
    CommercialAnchor(
        "dashboard-api-backed-state",
        "apps/dashboard/src/app.mjs",
        ("fetchA3DashboardSnapshot", "renderReportCenter", "renderReleaseEvidenceSummary", "releaseEvidenceReadbacks"),
        "A3",
        "Keeps dashboard wired to API-backed report/release evidence surfaces.",
    ),
    CommercialAnchor(
        "dashboard-typed-api-client",
        "apps/dashboard/src/api-client.mjs",
        ("fetchA3DashboardSnapshot", "fetchA3ReportCenter", "createShareableA3Report", "fetchA3AdminConsole"),
        "A3",
        "Keeps browser UI calls centralized instead of ad hoc fetch blobs.",
    ),
    CommercialAnchor(
        "typescript-sdk-mainline",
        "packages/ts/ashr-clone/package.json",
        ('"build": "tsc -p tsconfig.json"', '"test": "npm run build && node --test test/*.test.mjs"'),
        "A1/A3",
        "Keeps TypeScript as a typed SDK/client mainline with a build gate.",
    ),
    CommercialAnchor(
        "a3-api-commercial-routes",
        "services/report/a3_api_server.mjs",
        ("/api/a3/import/a1-run-result", "/api/a3/import/a2-grade-result", "/api/a3/reports/share", "api\\/a3\\/releases"),
        "A3",
        "Keeps A3 API-backed ingestion, hosted reports, and release evidence online.",
    ),
    CommercialAnchor(
        "a3-store-commercial-contract",
        "services/report/a3_store.mjs",
        ("A3_DB_CONTRACT", "release_evidence_readbacks", "POST /api/a3/import/a1-run-result", "GET /api/a3/usage/ledger"),
        "A3",
        "Keeps DB/API/event contract anchors for tenant-scoped SaaS state.",
    ),
    CommercialAnchor(
        "a3-report-commercial-export",
        "services/report/report_builder.mjs",
        ("summarizeReleaseGate", "summarizeReleaseEvidenceSummary", "summarizeCommercialReadiness", "buildJsonReport"),
        "A3",
        "Keeps release gate, evidence, commercial readiness, and exports linked.",
    ),
    CommercialAnchor(
        "a3-release-evidence-authority",
        "services/report/a3_release_evidence.mjs",
        ("a3.release_evidence_summary.v2", "buildReleaseEvidenceHealth", "diffReleaseEvidenceSummaries"),
        "A3",
        "Keeps release evidence as an authority object, not a static UI label.",
    ),
    CommercialAnchor(
        "a3-readback-worker",
        "services/report/a3_readback_capture_cli.mjs",
        ("--submit", "--output-receipt", "releaseReadbackEndpoint", "sanitizeReadback"),
        "A3",
        "Keeps the CI/worker path for external release-control readback.",
    ),
    CommercialAnchor(
        "a1-runtime-evidence-schema",
        "docs/a1/schemas/evidence_index.schema.json",
        ("schema_version", "status_counts", "function_counts", "records"),
        "A1",
        "Keeps A3 evidence claims grounded in A1 runtime evidence contracts.",
    ),
    CommercialAnchor(
        "a1-worker-data-model",
        "docs/a1/schemas/worker_data_model.schema.json",
        ("tenant", "worker", "usage"),
        "A1",
        "Keeps SaaS ingestion and worker durability visible to CL.",
    ),
    CommercialAnchor(
        "a2-grade-contract",
        "docs/a2/schemas/grade_results.schema.json",
        ("GradeResult", "score", "passed", "primary_failure_class"),
        "A2",
        "Keeps A3 dashboard/report claims grounded in A2 judge output.",
    ),
    CommercialAnchor(
        "a2-commercial-readiness-contract",
        "docs/a2/schemas/commercial_readiness.schema.json",
        ("commercial_readiness", "ready_for_commercial_gate", "gate_status"),
        "A2",
        "Keeps commercial gating tied to A2 policy evidence.",
    ),
    CommercialAnchor(
        "a3-api-server-tests",
        "tests/a3/a3_api_server.test.mjs",
        ("dashboard", "readback", "usage", "shareable"),
        "A3",
        "Keeps API-backed A3 routes covered by tests.",
    ),
    CommercialAnchor(
        "a3-dashboard-wiring-tests",
        "tests/a3/dashboard_wiring.test.mjs",
        ("releaseEvidenceReadbacks", "raw A1", "raw A2", "SaaS admin"),
        "A3",
        "Keeps UI wiring tied to A1/A2 sources and SaaS surfaces.",
    ),
    CommercialAnchor(
        "a3-report-builder-tests",
        "tests/a3/report_builder.test.mjs",
        ("Commercial Readiness", "Release Evidence Summary", "A2 G3", "raw A1"),
        "A3",
        "Keeps exported report evidence calibrated to A1/A2 and commercial readiness.",
    ),
    CommercialAnchor(
        "a3-sqlite-store-tests",
        "tests/a3/a3_sqlite_store.test.mjs",
        ("SQLite", "A1/A2", "usage", "readback"),
        "A3",
        "Keeps local DB path from drifting away from API/report evidence.",
    ),
    CommercialAnchor(
        "a3-acceptance-commercial-ledger",
        "docs/a3/acceptance_checklist.md",
        ("API-backed", "A1/A2", "Release Evidence", "usage"),
        "A3",
        "Keeps completed commercial acceptance items discoverable.",
    ),
)

COMMERCIAL_ADVISORIES: tuple[CommercialAnchor, ...] = (
    CommercialAnchor(
        "playwright-ts-e2e-mainline",
        "playwright.config.ts",
        ("@playwright/test", "apps/dashboard"),
        "A3",
        "A3 needs a Playwright TS E2E lane for login, dashboard, review, billing, and report flows.",
    ),
    CommercialAnchor(
        "tailwind-product-system",
        "tailwind.config.ts",
        ("content", "apps/dashboard"),
        "A3",
        "A3 should move visual density and product styling toward Tailwind or an equivalent design-system layer.",
    ),
    CommercialAnchor(
        "mobile-expo-client-surface",
        "apps/mobile/package.json",
        ("expo", "react-native"),
        "A3",
        "Mobile approval/release alert surfaces should use React Native / Expo when they become active scope.",
    ),
    CommercialAnchor(
        "wechat-mini-program-client-surface",
        "apps/wechat-miniprogram/project.config.json",
        ("appid", "miniprogramRoot"),
        "A3",
        "China commercial entry should have an explicit WeChat mini program surface when it becomes active scope.",
    ),
)

@dataclass
class Plan:
    changed_files: list[str]
    full: bool = False
    python: bool = False
    a3: bool = False
    typescript: bool = False
    go: bool = False
    rust: bool = False
    integration: bool = False
    evidence: bool = False
    reasons: dict[str, list[str]] = field(default_factory=dict)

    def mark(self, area: str, path: str) -> None:
        setattr(self, area, True)
        self.reasons.setdefault(area, []).append(path)

    def to_json(self) -> dict[str, object]:
        return {
            "changed_files": self.changed_files,
            "full": self.full,
            "python": self.python or self.full,
            "a3": self.a3 or self.full,
            "typescript": self.typescript or self.full,
            "go": self.go or self.full,
            "rust": self.rust or self.full,
            "integration": self.integration or self.full,
            "evidence": self.evidence or self.full,
            "reasons": self.reasons,
        }


def run_git(args: list[str], *, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def changed_files(base: str | None, head: str | None) -> list[str]:
    if not base or not head:
        return [normalize_path(p) for p in run_git(["ls-files"]).splitlines() if p.strip()]
    output = run_git(["diff", "--name-only", f"{base}...{head}"])
    return sorted({normalize_path(p) for p in output.splitlines() if p.strip()})


def matches_any(path: str, prefixes: Iterable[str] = (), suffixes: Iterable[str] = ()) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes) or any(path.endswith(suffix) for suffix in suffixes)


def build_plan(paths: list[str], *, full: bool = False) -> Plan:
    plan = Plan(changed_files=paths, full=full)
    if not paths:
        return plan

    for path in paths:
        if path in {".gitattributes", ".gitignore"} or path.startswith(".github/workflows/") or path == "scripts/cl_guard.py":
            plan.full = True
            plan.reasons.setdefault("full", []).append(path)

        if matches_any(
            path,
            prefixes=(
                "packages/sdk/ashr_clone/",
                "services/api/",
                "services/runner/",
                "services/judge/",
                "scripts/a2_",
                "tests/a1/",
                "tests/a2/",
                "fixtures/a2/",
                "docs/a1/",
                "docs/a2/",
            ),
            suffixes=(".py",),
        ):
            plan.mark("python", path)

        if matches_any(
            path,
            prefixes=(
                "apps/dashboard/",
                "services/report/",
                "tests/a3/",
                "fixtures/a3/",
                "docs/a3/",
                "docs/screenshots/",
            ),
        ):
            plan.mark("a3", path)

        if path.startswith("packages/ts/ashr-clone/") or path in {
            "docs/a1/schemas/run_fixture.schema.json",
            "docs/a1/schemas/agent_turn.schema.json",
            "docs/a1/schemas/vm_stream_frame.schema.json",
        }:
            plan.mark("typescript", path)

        if path.startswith("packages/go/ashrclone/") or path.startswith("tests/integration/go/"):
            plan.mark("go", path)

        if path.startswith("packages/rust/ashr-runtime-verify/"):
            plan.mark("rust", path)

        if path.startswith("tests/integration/") or path.startswith("infra/") or path.startswith("services/api/migrations/"):
            plan.mark("integration", path)
            if path.endswith(".py") or path.startswith("services/api/migrations/"):
                plan.mark("python", path)

        if (
            path == ".gitattributes"
            or path.startswith(PINNED_A3_ARTIFACT_PREFIXES)
            or path in {
                "services/report/a3_gate_cli.mjs",
                "services/report/a3_audit_archive.mjs",
                "tests/a3/a3_gate_cli.test.mjs",
                "tests/a3/a3_audit_archive.test.mjs",
            }
        ):
            plan.mark("evidence", path)
            if path.startswith("fixtures/a3/") or path.startswith("services/report/") or path.startswith("tests/a3/"):
                plan.mark("a3", path)

    return plan


def tracked_files() -> list[str]:
    return [normalize_path(p) for p in run_git(["ls-files"]).splitlines() if p.strip()]


def should_skip_file(path: str) -> bool:
    normalized = normalize_path(path)
    if any(normalized.startswith(prefix) for prefix in SKIP_DIR_PREFIXES):
        return True
    return Path(normalized).suffix.lower() in BINARY_SUFFIXES


def scan_secrets() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel in tracked_files():
        if should_skip_file(rel):
            continue
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            if any(hint in lowered for hint in NON_SECRET_HINTS):
                continue
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append({"type": name, "path": rel, "line": lineno})
    return findings


def check_pinned_line_endings() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel in tracked_files():
        if not rel.startswith(PINNED_A3_ARTIFACT_PREFIXES):
            continue
        if not rel.endswith(PINNED_A3_ARTIFACT_SUFFIXES):
            continue
        data = (ROOT / rel).read_bytes()
        if b"\r\n" in data:
            findings.append({"path": rel, "issue": "CRLF in hash-pinned A3 artifact"})
    return findings


def check_private_paths_tracked() -> list[dict[str, object]]:
    blocked_prefixes = (".secrets/", "docs/evidence/private_refs/", "tmp/", "output/", "recon/")
    return [
        {"path": rel, "issue": "private/generated path is tracked"}
        for rel in tracked_files()
        if rel.startswith(blocked_prefixes)
    ]


def check_anchor(anchor: CommercialAnchor) -> dict[str, object] | None:
    path = ROOT / anchor.path
    if not path.exists():
        return {
            "anchor_id": anchor.anchor_id,
            "path": anchor.path,
            "lane": anchor.lane,
            "purpose": anchor.purpose,
            "issue": "missing_file",
            "missing": [anchor.path],
        }
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as error:
        return {
            "anchor_id": anchor.anchor_id,
            "path": anchor.path,
            "lane": anchor.lane,
            "purpose": anchor.purpose,
            "issue": "unreadable_file",
            "error": str(error),
        }
    missing = [needle for needle in anchor.contains if needle not in text]
    if missing:
        return {
            "anchor_id": anchor.anchor_id,
            "path": anchor.path,
            "lane": anchor.lane,
            "purpose": anchor.purpose,
            "issue": "missing_anchor_text",
            "missing": missing,
        }
    return None


def check_commercial_anchors() -> dict[str, object]:
    blockers = [finding for anchor in COMMERCIAL_ANCHORS if (finding := check_anchor(anchor))]
    advisories = [finding for anchor in COMMERCIAL_ADVISORIES if (finding := check_anchor(anchor))]
    return {
        "status": "failed" if blockers else "passed",
        "schema_version": "ashr.cl_guard.commercial.v1",
        "blocker_count": len(blockers),
        "advisory_count": len(advisories),
        "checked_blocker_count": len(COMMERCIAL_ANCHORS),
        "checked_advisory_count": len(COMMERCIAL_ADVISORIES),
        "blockers": blockers,
        "advisories": advisories,
        "commercial_summary": {
            "a3_mainline": "Product Console / Review Workflow / Report Center / GitHub Gate / Commercial UI",
            "typescript_mainline": True,
            "a1_a2_calibration_required": True,
            "advisories_block_pr": False,
        },
    }


def write_github_outputs(plan: dict[str, object], output_path: str) -> None:
    keys = ("full", "python", "a3", "typescript", "go", "rust", "integration", "evidence")
    with open(output_path, "a", encoding="utf-8") as fh:
        for key in keys:
            fh.write(f"{key}={str(bool(plan[key])).lower()}\n")
        fh.write(f"changed_count={len(plan['changed_files'])}\n")


def write_summary(plan: dict[str, object], summary_path: str) -> None:
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("## Ashr CL Gate plan\n\n")
        fh.write(f"Changed files: {len(plan['changed_files'])}\n\n")
        fh.write("| Area | Run? | Reason count |\n|---|---:|---:|\n")
        reasons = plan.get("reasons", {})
        for key in ("full", "python", "a3", "typescript", "go", "rust", "integration", "evidence"):
            run = bool(plan.get(key))
            count = len(reasons.get(key, [])) if isinstance(reasons, dict) else 0
            fh.write(f"| {key} | {str(run).lower()} | {count} |\n")


def command_plan(args: argparse.Namespace) -> int:
    paths = changed_files(args.base, args.head)
    plan = build_plan(paths, full=args.full).to_json()
    print(json.dumps(plan, indent=2, sort_keys=True))
    if args.github_output:
        write_github_outputs(plan, args.github_output)
    if args.summary:
        write_summary(plan, args.summary)
    return 0


def command_hygiene(_: argparse.Namespace) -> int:
    all_findings: list[dict[str, object]] = []
    for label, findings in (
        ("secret", scan_secrets()),
        ("line_endings", check_pinned_line_endings()),
        ("private_paths", check_private_paths_tracked()),
    ):
        for finding in findings:
            all_findings.append({"gate": label, **finding})

    if all_findings:
        print(json.dumps({"status": "failed", "findings": all_findings}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": "passed", "findings": []}, indent=2, sort_keys=True))
    return 0


def command_commercial(_: argparse.Namespace) -> int:
    result = check_commercial_anchors()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ashr selective CL gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Build selective CI plan from changed files")
    plan_parser.add_argument("--base")
    plan_parser.add_argument("--head", default="HEAD")
    plan_parser.add_argument("--full", action="store_true")
    plan_parser.add_argument("--github-output")
    plan_parser.add_argument("--summary")
    plan_parser.set_defaults(func=command_plan)

    hygiene_parser = subparsers.add_parser("hygiene", help="Run high-confidence repository blockers")
    hygiene_parser.set_defaults(func=command_hygiene)

    commercial_parser = subparsers.add_parser("commercial", help="Run commercial SaaS anchor checks")
    commercial_parser.set_defaults(func=command_commercial)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
