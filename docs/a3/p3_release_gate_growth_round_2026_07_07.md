# P3 Release Gate Growth Round - 2026-07-07

## Goal

Move A3 from a dashboard demo toward a commercial Agent Release Intelligence console. This round focuses on the thing a buyer can understand immediately: should this agent release be allowed to ship?

## 20 Growth Points Considered

1. Release Gate decision: approve / needs review / block release.
2. PR gate payload for future GitHub required checks.
3. Risk score based on pass rate, policy failures, missing tools, and trace coverage.
4. Required approver list.
5. Top risk cases for reviewer attention.
6. Print/PDF executive sign-off section.
7. JSON export field for machine-readable release decisions.
8. Markdown section for PR/release notes.
9. Dashboard Release Gate panel.
10. Release checks for pass rate.
11. Release checks for critical/blocker failures.
12. Release checks for unsafe/policy failures.
13. Release checks for missing required tools.
14. Release checks for trace completeness.
15. Release checks for A2 coverage health.
16. Release checks for signed media safety.
17. Commercial explanation text for enterprise reviewers.
18. Tests for blocked risky evidence.
19. Tests for approved clean evidence.
20. Screenshot evidence for run `11926`.

## What Landed

Implemented in code:

- `summarizeReleaseGate()` in `services/report/report_builder.mjs`
- `release_gate` in JSON export
- `## Release Gate` in Markdown export
- Release Gate section in print/PDF preview
- Release Gate dashboard panel
- Release Gate wiring tests
- Release Gate behavior tests

The release gate currently evaluates:

| Check | Purpose |
|---|---|
| `pass_rate` | Blocks weak release candidates before customers see them. |
| `critical_failures` | Stops releases with critical/blocker cases. |
| `policy_failures` | Sends unsafe or forbidden-tool behavior to safety review. |
| `required_tool_coverage` | Catches agents that skipped required tools. |
| `trace_evidence` | Ensures release evidence is replayable/auditable. |
| `coverage_minimums` | Uses A2 coverage health when available. |
| `media_safety` | Keeps live signed media disabled until safety is proven. |

## Result For Official Demo Run 11926

Current source:

- Dataset: `884`
- Run: `11926`
- Cases: 5
- Pass/fail: 2 pass / 3 fail
- Pass rate: 40%
- Average score: 56.4

Release Gate result:

- Decision: `Block release`
- Risk score: 70
- Failed checks: 2
- Blocks merge: yes
- Required approvers: 4

Main blockers:

- Pass rate is only 40%, below the 95% commercial release threshold.
- One case has `missing_required_tool`, which can hide production incident risk.

## Evidence

Tests:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 43
pass 43
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`
- Confirmed Release Gate shows `Block release`
- Confirmed risk score, failed checks, blockers, and approvers render

Screenshot:

- `docs/screenshots/a3-dashboard-release-gate-11926.png`

## Growth-Auditor Finding

Growth-Auditor rated A3 as closer to a paid pilot than a toy:

- Sales narrative: about 7/10
- Customer pilot readiness: about 5.5/10
- Enterprise self-host readiness: about 3/10

Strongest commercial direction:

1. Enterprise PR Gate / Release Intelligence
2. Incident Replay and RCA
3. Self-host compliance edition
4. Audit export bundle
5. Usage governance and chargeback

## What Is Still Not Enterprise-Ready

- Release Gate is local dashboard/report logic, not a GitHub required check yet.
- No persistent reviewer workflow.
- No waiver / expiry / approval audit trail.
- No backend service or database.
- No SSO/RBAC/self-host installer.
- Official Ashr frontend still does not visually list API-created run `11926` in Results.

## Next Parallel Growth Points

1. Add CLI command shape: `ashr gate --json`.
2. Generate GitHub Check Run payload from `release_gate`.
3. Add PR comment Markdown template.
4. Add waiver object with owner, reason, expiry, and blocked checks.
5. Add reviewer assignment state.
6. Add release version/environment fields.
7. Add incident replay pack from failed cases.
8. Add run-to-run regression comparison.
9. Add configurable thresholds fixture.
10. Add audit manifest with file hashes.
11. Add redaction log to export bundle.
12. Add self-host readiness panel.
13. Add RBAC/SSO placeholder contract.
14. Add usage metering by run/case/tool/media.
15. Add billing forecast placeholder.
16. Add Jira/Slack/PagerDuty handoff templates.
17. Add official frontend visual confirmation for run `11926`.
18. Add native failure-class adapter if Ashr exposes one.
19. Add signed media sandbox only after URL safety is confirmed.
20. Add backend persistence plan for enterprise console.
