# A3 Live GitHub Check Publisher - 2026-07-08

## Goal

Move A3 PR Gate from "can generate a GitHub Check payload" to "can publish a GitHub Check Run when CI explicitly opts in."

This is a commercial release-control step: a customer can wire ReleaseFoundry into a pull request, publish the gate result as a GitHub Check, and then make that check required through repository branch protection.

## Added capability

- Added `publishGitHubCheckRun(...)` in `services/report/a3_github_integration.mjs`.
- Added `services/report/a3_github_publish_cli.mjs`.
- Added dry-run by default:
  - no GitHub API call unless `dryRun: false` or CLI `--live` is used
  - no token required for dry-run
  - dry-run receipt is safe to commit
- Added live opt-in:
  - uses a runtime token from `GITHUB_TOKEN`, `GH_TOKEN`, or `--token-env`
  - sends `POST /repos/{owner}/{repo}/check-runs` or `PATCH /check-runs/{id}`
  - stores only sanitized receipt fields
- Updated `docs/a3/p3_github_action_workflow_example.yml` to publish the ReleaseFoundry Check Run in GitHub Actions.
- Saved dry-run evidence:
  - `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json`

## Important boundary

This pass adds a live-capable GitHub Check Run publisher. It does not itself configure GitHub branch protection.

To make the check truly required, a repository admin must configure branch protection and require the check named:

```text
ReleaseFoundry Release Gate
```

That branch-protection step should be recorded as separate evidence before claiming "required check is fully enforced in GitHub."

## A1/A2/A3 compatibility

- A1 data remains the source of run, case, trace, observation, and tool-call evidence.
- A2 data remains the source of score, pass/fail, judge evidence, coverage, severity, and failure class.
- A3 only publishes the release decision after report/gate generation.
- The GitHub publisher does not change A1 runner logic, A2 judge semantics, or A3 report schema.
- Existing dry-run builders still return the same request shapes.

## Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
13 tests
13 pass
0 fail
```

Covered cases:

- check request builder remains dry-run and secret-free
- PR comment upsert planner remains plan-only
- publisher defaults to dry-run and does not call fetch
- live opt-in posts with a runtime token in tests
- live receipt excludes token, Authorization header, and Bearer value
- missing token in live mode fails before fetch
- failed GitHub response is sanitized
- CLI writes dry-run receipt without posting
- committed fixture and workflow example stay redacted

## Safety boundary

- No `.env.local` was read.
- No ReleaseFoundry API call was made.
- No live GitHub API call was made in this pass.
- No GitHub token, API key, cookie, email, raw signed URL, or Authorization header was committed.
- The only committed receipt is dry-run and redacted.

## Growth-Auditor notes

### New sellable capability

A3 now has a concrete route from local release evidence to a CI-visible GitHub Check Run. This is closer to a paid release-intelligence product because it can sit in the customer's PR workflow instead of remaining a dashboard-only report.

### Still not final commercial-grade

- Branch protection is not configured by code.
- PR comment live publisher is still plan-only.
- GitHub App installation flow is not implemented.
- Customer repository onboarding and permission checks are still missing.
- The check is not yet connected to durable reviewer identity binding.

### Next 20 growth points

1. Add a dry-run branch-protection plan builder for required checks.
2. Add a live branch-protection publisher behind explicit admin opt-in.
3. Add a PR comment live publisher with marker-based update and sanitized receipts.
4. Add GitHub App installation readiness docs and permission audit.
5. Add a GitHub Actions end-to-end dry-run fixture that includes gate, check receipt, PR comment, and audit bundle.
6. Add check-run update mode receipt fixture.
7. Add dashboard panel showing GitHub Check publish status.
8. Add report JSON field for GitHub publish receipt.
9. Add report center artifact entry for GitHub check publish receipt.
10. Add audit bundle hashing for the publish receipt.
11. Add immutable archive packaging for gate/report/check/comment/receipt artifacts.
12. Add branch-protection evidence capture checklist.
13. Add reviewer identity binding to check-run annotations.
14. Add GitHub actor/source metadata to review workflow records.
15. Add enterprise self-host config for GitHub API base URL.
16. Add retry/backoff and rate-limit handling for live GitHub calls.
17. Add 403/404/422 GitHub error-shape fixtures.
18. Add usage ledger meter for CI gate runs and published checks.
19. Add customer onboarding guide for "make ReleaseFoundry required before merge."
20. Add Growth-Auditor scoring that ranks PR Gate, audit bundle, review workflow, and self-host readiness by commercial value.
