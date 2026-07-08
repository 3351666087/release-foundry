# P3 Gate CLI Growth Round - 2026-07-07

## Goal

Turn A3's local dashboard release decision into a command-shaped artifact that can later become a GitHub required check:

```text
ashr gate --json
```

This round does not call the live GitHub Checks API yet. It creates the tested local contract that a CI job or PR integration can consume.

## 20 Growth Points Covered

1. CLI-shaped entrypoint for release gate evaluation.
2. JSON output contract: `a3.gate_cli.v1`.
3. Markdown output renderer for humans.
4. Failing exit-code hint for blocked releases.
5. Machine-readable GitHub check payload included in CLI output.
6. PR comment body included in CLI output.
7. Waiver policy included in CLI output.
8. Reviewer lanes included in CLI output.
9. Incident replay case list included in CLI output.
10. Audit manifest included in CLI output.
11. SHA-256 file hashes for input artifacts.
12. Portable manifest paths without local absolute user directories.
13. Configurable commercial thresholds fixture.
14. Threshold values surfaced in release gate output.
15. Redacted CLI evidence fixture.
16. Tests for programmatic builder output.
17. Tests for real command execution.
18. Tests for redacted evidence fixture shape.
19. Secret/path scan check for generated evidence.
20. Worklog and checklist evidence.

## What Landed

Code:

- `services/report/a3_gate_cli.mjs`
  - Adds `buildGateCliPayload()`.
  - Adds `renderGateCliMarkdown()`.
  - Supports `--runs`, `--grades`, `--coverage`, `--thresholds`, `--release-version`, `--environment`, `--owner`, `--source`, `--head-sha`, `--details-url`, `--annotation-path`, `--json`, `--markdown`, `--strict-exit`, `--no-fail`, `--output-json`, `--output-md`, `--output-check`, and `--output-pr-comment`.
  - Emits JSON suitable for future CI/PR gate integration.
  - Emits a GitHub Check Run payload with annotations for top-risk cases.
  - Emits a PR comment Markdown file for release review.
  - Produces audit manifest hashes.
  - Writes workspace-relative artifact paths so local user directories are not exposed.
  - Applies a lightweight output redaction scrubber for emails, bearer tokens, API key assignments, generic secret tokens, cookies, and signed media URLs.
- `services/report/report_builder.mjs`
  - Adds configurable release thresholds while preserving current defaults.
  - Surfaces threshold values in `release_gate`.
  - Lets `summarizeReleaseWorkflow()` consume threshold config.

Fixtures:

- `fixtures/a3/release_gate_thresholds.json`
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
- `fixtures/a3/p3/a3_gate_cli_report.redacted.md`

Tests:

- `tests/a3/a3_gate_cli.test.mjs`

## Example Command

```text
node services/report/a3_gate_cli.mjs --runs fixtures/a3/mock_run_results.json --grades fixtures/a3/mock_grade_results.json --coverage fixtures/a2/results/a2_g3_coverage_report.json --thresholds fixtures/a3/release_gate_thresholds.json --release-version local-mock-commercial-gate --source a3-local-mock --head-sha local-demo-head-sha --details-url https://example.invalid/a3-gate-demo --annotation-path docs/a3/p3_gate_cli_growth_2026_07_07.md --output-check fixtures/a3/p3/a3_gate_cli_github_check.redacted.json --output-pr-comment fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md --output-md fixtures/a3/p3/a3_gate_cli_report.redacted.md --json --no-fail
```

Use `--strict-exit` for CI, where blocked evidence should exit nonzero and block a PR merge. Use `--no-fail` for local report generation, where the JSON should still record `exit_code_hint: 1` but the process exits 0.

## Current Evidence Result

For the local A1/A2-generated mock fixture:

- Runs: 1
- Cases: 32
- Pass rate: 6.3%
- Failed cases: 30
- Decision: `Block release`
- Risk score: 100
- GitHub check conclusion: `failure`
- Blocks merge: yes
- Failed checks:
  - `pass_rate`
  - `critical_failures`
  - `policy_failures`
  - `required_tool_coverage`

The redacted evidence fixture is saved at:

- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
- `fixtures/a3/p3/a3_gate_cli_report.redacted.md`

## Verification

Focused test:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 7
pass 7
fail 0
```

Full A3 test command:

```text
node --test tests/a3/a3_gate_cli.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

## API Calibration Note

This round did not create new live Ashr data. It uses existing A3/A2 fixtures and the existing P3 evidence chain. The purpose was to package the already-calibrated evidence into a CI/PR-consumable contract.

No API key, token, cookie, email, header, or live signed media URL was printed or saved.

## Commercial Value

This is the first command-shaped A3 release artifact. It moves A3 closer to the product customers actually pay for:

- CI can fail risky agent releases.
- GitHub Checks can show top-risk case annotations.
- PR reviewers get a clear comment.
- Managers get an audit manifest.
- Security/compliance reviewers get hashes and redaction policy.
- Failed cases become an incident replay list.

## Remaining Gaps

- The CLI is not wired to GitHub Checks yet.
- Waivers are still policy output, not persisted approvals.
- Audit manifest hashes input files, but not every generated export artifact yet.
- Thresholds are local JSON config, not tenant/project policy from a backend.
- Output redaction is lightweight pattern scrubbing, not a full data-loss-prevention engine.

## Next Growth Points

1. Add GitHub Check Run API adapter.
2. Add PR comment writer for GitHub Issues/Pulls.
3. Add audit manifest for generated JSON/Markdown/PDF exports.
4. Add stronger redaction log export with per-field provenance.
5. Add enforced output scrubber failure mode.
6. Add persisted waiver fixture.
7. Add signed reviewer approval fixture.
8. Add waiver expiry validation.
9. Add follow-up issue validation.
10. Add run-to-run regression diff.
11. Add release war room panel.
12. Add incident replay UI panel.
13. Add Slack handoff template.
14. Add Jira handoff template.
15. Add PagerDuty handoff template.
16. Add self-host readiness panel.
17. Add RBAC/SSO contract stub.
18. Add usage metering by run/case/tool/media.
19. Add billing forecast placeholder.
20. Add official frontend Results recheck for run `11926`.

## Follow-Up Landed: GitHub Dry-Run Adapter

The first two next growth points have now been converted into a dry-run integration contract:

- `services/report/a3_github_integration.mjs`
- `tests/a3/a3_github_integration.test.mjs`
- `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- `docs/a3/p3_github_action_workflow_example.yml`
- `docs/a3/p3_github_dry_run_integration_2026_07_07.md`

This is still not a live GitHub required check. It is the tested request shape that should be reviewed before the team allows a real token or GitHub App installation to send checks/comments.
