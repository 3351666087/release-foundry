# P3 PR Gate Workflow Growth Round - 2026-07-07

## Goal

Move A3 from a local Release Gate into a workflow that can plug into a real engineering release process: GitHub check, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay pack.

## 20 Growth Points Covered

1. GitHub Check Run payload shape.
2. PR comment Markdown template.
3. Machine-readable `release_workflow` JSON export.
4. Waiver policy with required fields.
5. Blocked-release exceptional waiver rule.
6. Waiver expiry maximums.
7. Reviewer workflow state.
8. Reviewer lanes for release, safety, runner/tooling, judge, evidence, and A3 triage.
9. Release version field.
10. Environment field.
11. Owner field.
12. Top-risk incident replay case list.
13. Audit bundle manifest.
14. Required audit artifacts.
15. Optional screenshot artifact policy.
16. Redaction policy for audit exports.
17. Dashboard PR Gate & Audit panel.
18. Print/PDF PR Gate & Audit section.
19. Markdown PR Gate / Review Workflow section.
20. Tests proving risky evidence produces a failing check and audit package.

## What Landed

Code:

- `services/report/report_builder.mjs`
  - Added `summarizeReleaseWorkflow()`.
  - Added GitHub check payload shape.
  - Added PR comment Markdown template.
  - Added waiver policy.
  - Added reviewer workflow.
  - Added audit bundle manifest.
  - Added incident replay pack.
  - Added `release_workflow` to JSON export.
  - Added `## PR Gate / Review Workflow` to Markdown export.
- `apps/dashboard/index.html`
  - Added sidebar link for `PR Gate`.
  - Added `PR Gate & Audit` dashboard panel.
  - Added PR workflow metrics, review lanes, waiver policy, and audit bundle artifact list.
  - Added PR Gate & Audit section to the print-ready report preview.

Tests:

- `tests/a3/report_builder.test.mjs`
  - Added coverage for PR check, waiver, audit bundle, and incident replay.
- `tests/a3/dashboard_wiring.test.mjs`
  - Added wiring checks for dashboard PR Gate & Audit panel and print report section.

Screenshot:

- `docs/screenshots/a3-dashboard-pr-gate-audit-11926.png`

## Current Result For Official Demo Run 11926

The loaded official demo still represents a blocked release:

- Dataset: `884`
- Run: `11926`
- Cases: 5
- Pass/fail: 2 pass / 3 fail
- Pass rate: 40%
- Average score: 56.4

New PR workflow result:

- GitHub check name: `Ashr++ Release Gate`
- Check conclusion: `failure`
- Blocks merge: yes
- Waiver required: yes
- Waiver mode: exceptional only for blocked releases
- Waiver max expiry: 1 day
- Incident replay mode: failed cases first
- Audit manifest: `a3.audit_bundle.v1`

## API Calibration Note

This round did not create a new Ashr hosted run or call a new mutating API. The workflow uses existing redacted official-demo evidence for dataset `884` / run `11926`:

- `fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json`
- `fixtures/a3/p3/ashr_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`

No key, token, cookie, email, header, or live signed media URL was printed or written.

## Verification

Command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 44
pass 44
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed `PR Gate & Audit` renders check conclusion `failure`, blocks merge `yes`, waiver required `yes`, waiver max `1d`, and audit bundle artifacts.
- Saved screenshot under `docs/screenshots/a3-dashboard-pr-gate-audit-11926.png`.

## Growth-Auditor Finding

Growth-Auditor's read-only audit agrees that the closest commercial path is:

1. Enterprise PR Gate / Release Intelligence.
2. Incident Replay and RCA.
3. Audit Export Bundle.
4. Self-host Compliance Edition.

This round directly advances the first three by turning A3's local release decision into PR-facing and audit-facing artifacts.

## Remaining Gaps

- This is still not a live GitHub required check.
- There is no persistent backend approval trail yet.
- Waivers are generated as policy data, not stored as signed approvals.
- Audit artifacts have paths and policy, but no file hashes yet.
- Official Ashr frontend Results visibility for run `11926` still needs logged-in visual confirmation.

## Next Growth Points

1. Add a CLI command shape for `ashr gate --json`.
2. Add file-hash audit manifest.
3. Add redaction log export.
4. Add run-to-run regression diff.
5. Add configurable release thresholds fixture.
6. Add persistent waiver fixture.
7. Add reviewer sign-off fixture.
8. Add release war room panel.
9. Add incident replay UI panel.
10. Add GitHub PR comment export button.
11. Add Jira handoff template.
12. Add Slack handoff template.
13. Add PagerDuty incident replay handoff template.
14. Add self-host readiness panel.
15. Add SSO/RBAC contract stub.
16. Add usage metering by run/case/tool/media.
17. Add billing forecast placeholder.
18. Add native Ashr failure-class adapter if the API exposes it.
19. Add signed media sandbox only after URL safety is confirmed.
20. Add backend persistence plan.
