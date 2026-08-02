# A3 PR Comment Publisher and Required Check Plan - 2026-07-08

## Goal

Continue turning A3 PR Gate into a real release-control workflow:

- publish a human-readable PR comment when CI explicitly opts in
- generate a safe branch-protection plan for making `ReleaseFoundry Release Gate` required

## Added capability

- Added `publishPrCommentUpsert(...)` in `services/report/a3_github_integration.mjs`.
- Added `buildBranchProtectionRequiredCheckPlan(...)` in `services/report/a3_github_integration.mjs`.
- Extended `services/report/a3_github_publish_cli.mjs` with explicit PR comment mode:
  - `--pr-comment`
  - `--pull-number <number>`
  - still dry-run by default
  - live mode only with explicit `--live`
- Updated `docs/a3/p3_github_action_workflow_example.yml` with `Publish ReleaseFoundry PR Comment`.
- Saved redacted evidence:
  - `fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json`
  - `fixtures/a3/p3/a3_github_required_check_plan.redacted.json`

## Safety boundary

- Existing `buildPrCommentUpsertPlan(...)` remains plan-only.
- Existing GitHub Check publisher behavior remains unchanged.
- `--live` alone still publishes only the Check Run path; PR comments require explicit `--pr-comment`.
- Branch protection is not modified by code.
- No `.env.local`, ReleaseFoundry key, GitHub token, cookie, email, Authorization header, or raw signed URL was read or committed.

## A1/A2 compatibility

- A1 remains the source of run, case, trace, observation, and tool-call evidence.
- A2 remains the source of grade, score, pass/fail, coverage, severity, and failure class.
- A3 uses that evidence to produce release gate, GitHub Check, PR comment, and audit artifacts.
- This pass does not change A1 runner logic, A2 judge semantics, or A3 report normalization.

## Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
21 tests
21 pass
0 fail
```

Covered:

- PR comment dry-run does not call fetch
- live create comment path
- live update existing marker comment path
- lookup failure stops before comment mutation
- CLI requires `--pull-number` for `--pr-comment`
- branch protection plan is plan-only and names `ReleaseFoundry Release Gate`

## Remaining production gap

The repository maintainer still needs to configure branch protection before the check is actually required. The current branch-protection artifact is a plan and evidence shape, not a live mutation.

## Growth-Auditor notes

### New sellable capability

Customers can now wire ReleaseFoundry into PR review with both machine-readable check status and human-readable release commentary.

### High-value next growth points

1. Live branch-protection publisher behind explicit admin opt-in.
2. Dashboard panel showing GitHub Check and PR comment publish receipts.
3. Report Center artifact entry for PR comment receipt.
4. Audit bundle hashing for check/comment publish receipts.
5. GitHub App installation guide and permission readiness.
6. 403/404/422 GitHub error-shape fixtures.
7. Rate-limit and retry handling for GitHub publish calls.
8. Usage ledger meter for published checks and PR comments.
9. Reviewer identity binding to GitHub actors.
10. Required-check verification command that reads branch protection.
11. PR comment markdown diff preview before publish.
12. Enterprise self-host GitHub API base URL config.
13. Signed immutable archive for gate/check/comment/report bundle.
14. Archive verifier for zip/tar audit bundles.
15. Hosted report link embedded into PR comment.
16. Incident replay links embedded into PR comment.
17. Waiver/approval status embedded into PR comment.
18. GitHub Action example that uploads final receipt artifacts after publishing.
19. Redaction firewall scan over publish receipts.
20. Growth-Auditor dashboard card ranking PR Gate readiness.
