# P3 GitHub Dry-Run Integration Growth Round - 2026-07-07

## Goal

Turn the A3 release gate payload into GitHub-shaped dry-run requests without calling the live GitHub API.

This round intentionally does not use a GitHub token and does not create comments or checks in a real repository. It creates the redacted request shapes, tests, and workflow example needed before a live integration is safe.

## 20 Growth Points Covered

1. GitHub Check Run create request builder.
2. GitHub Check Run update request builder.
3. PR comment create plan builder.
4. PR comment update plan builder.
5. Marker-based PR comment idempotency.
6. Explicit `headSha` requirement so stale fixture SHAs are not reused in CI.
7. `detailsUrl` override for CI run links.
8. Check annotations normalized to GitHub's 50-annotation limit.
9. Annotation fallback path, line, level, title, and message defaults.
10. Token scope documentation for Checks API.
11. Token scope documentation for PR comment writes.
12. Dry-run safety metadata on every generated request.
13. Redacted committed Check Run request fixture.
14. Redacted committed PR comment upsert fixture.
15. GitHub Actions workflow example for future CI setup.
16. Tests for create-check request shape.
17. Tests for update-check request shape.
18. Tests for PR comment create/update behavior.
19. Tests that committed fixtures do not contain bearer tokens or local user paths.
20. Worklog/checklist evidence for the next reviewer.

## What Landed

Code:

- `services/report/a3_github_integration.mjs`
  - Adds `buildGitHubCheckRunRequest()`.
  - Adds `buildPrCommentUpsertPlan()`.
  - Adds `buildGitHubActionWorkflowExample()`.
  - Keeps the integration dry-run only.
  - Requires the caller to provide a current `headSha`.
  - Allows CI to provide the current `detailsUrl`.

Fixtures and examples:

- `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- `docs/a3/p3_github_action_workflow_example.yml`

Tests:

- `tests/a3/a3_github_integration.test.mjs`

## Verification

Focused test:

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
tests 6
pass 6
fail 0
```

## API Calibration Note

No live GitHub API call was made in this pass. No GitHub token was read, printed, saved, or required. This round only proves the request contract that a future GitHub Action can send after the team approves a live integration.

No new Ashr hosted mutation was performed in this pass. The dry-run adapter uses existing redacted A3 gate evidence.

## Commercial Value

This moves A3 from "we can display a release gate" to "we can package that gate for a buyer's PR workflow." That matters commercially because enterprise customers usually need agent release quality to appear where they already approve software: GitHub checks and PR comments.

The current value is:

- A future CI job can create an `Ashr++ Release Gate` check.
- A future CI job can leave or update one stable PR comment.
- Reviewers can see top-risk cases without opening the dashboard first.
- The request contract can be audited before any live token is used.
- The workflow example gives the team a concrete path from local gate to CI gate.

## Remaining Gaps

- This is not a live GitHub required check yet.
- No token storage or GitHub App installation flow exists.
- No real PR comment is created yet.
- No check-run id persistence exists for update mode.
- No branch protection or required-check configuration exists.
- Reviewer approvals and waiver expiry are still local/report-level data, not signed enterprise records.

## Next Growth Points

1. Add a live GitHub writer behind an explicit dry-run/live flag.
2. Add a GitHub App installation contract instead of personal tokens.
3. Persist check-run ids per PR head SHA.
4. Persist PR comment ids per run id.
5. Add branch protection setup documentation.
6. Add a required-check policy fixture.
7. Add signed reviewer approval fixtures.
8. Add waiver expiry validation.
9. Add waiver owner validation.
10. Add audit hashes for generated JSON/Markdown/PDF exports.
11. Add DLP-style enforced redaction failure mode.
12. Add a release war room UI panel fed by PR gate output.
13. Add run-to-run regression diff in the PR comment.
14. Add incident replay links per top-risk case.
15. Add Slack handoff payload.
16. Add Jira issue handoff payload.
17. Add PagerDuty incident handoff payload.
18. Add self-host GitHub Enterprise Server base URL tests.
19. Add enterprise RBAC/SSO approval lanes.
20. Recheck official Ashr Results visibility for dataset `884` / run `11926`.
