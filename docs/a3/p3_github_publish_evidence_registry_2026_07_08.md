# A3 GitHub Publish Evidence Registry - 2026-07-08

## Goal

Bind GitHub publish receipts into A3's customer-facing evidence chain instead of leaving them as loose CLI artifacts.

This moves PR Gate closer to a commercial release-intelligence product: a reviewer can see not only the gate decision, but also the delivery evidence for GitHub Check, PR comment, and required-check planning.

## Added capability

- Added `summarizeGithubPublishEvidence(...)` in `services/report/report_builder.mjs`.
- Added `github_publish_evidence` to JSON report export.
- Added `## GitHub Publish Evidence` to Markdown report export.
- Added GitHub publish evidence control artifacts to Artifact Registry:
  - `github_check_publish_receipt`
  - `github_pr_comment_publish_receipt`
  - `github_required_check_plan`
- Added `github_pr_gate_packet` packet preset to Artifact Registry.
- Dashboard static sources now load redacted GitHub publish evidence fixtures.
- Dashboard Report Center / Artifact Registry can surface the GitHub publish artifacts.

## Evidence inputs

- `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json`
- `fixtures/a3/p3/a3_github_required_check_plan.redacted.json`

## Verification

```text
node --test tests/a3/artifact_registry.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
73 tests
73 pass
0 fail
```

## Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub API call was made.
- No branch-protection mutation was made.
- No token, cookie, email, Authorization header, raw signed URL, or local absolute user path was committed.
- CSV export still avoids GitHub publish evidence to reduce accidental spread of PR comment content.

## A1/A2 compatibility

- A1 remains the source of run, trace, observation, and tool-call evidence.
- A2 remains the source of score, pass/fail, failure class, coverage, and gate policy evidence.
- GitHub publish evidence is an A3 delivery receipt layer. It does not change A1 RunResult or A2 GradeResult semantics.
- `release_workflow.github_check` remains the planned PR gate output. `github_publish_evidence` is the publish/required-check evidence around that output.

## Growth-Auditor notes

### New sellable capability

A3 can now package PR Gate delivery evidence into the same report and artifact registry a customer would use for release sign-off and audit review.

### Still not commercial-final

- The committed receipts are dry-run evidence.
- Branch protection is planned but not live-configured.
- The publish receipts are not yet hashed into the immutable audit bundle.
- The dashboard does not yet have a dedicated GitHub Publish Evidence card outside Artifact Registry.

### Next 20 growth points

1. Add a dedicated GitHub Publish Evidence dashboard panel.
2. Add publish evidence to print/PDF report preview.
3. Add publish receipt hashes to audit bundle index.
4. Add publish receipt hashes to generated artifact manifest.
5. Add required-check verification command that reads branch protection.
6. Add live branch-protection publisher behind explicit maintainer approval.
7. Add API endpoint `GET /api/a3/github/publish/evidence`.
8. Add API endpoint `POST /api/a3/github/checks/dry-run`.
9. Add API endpoint `POST /api/a3/github/pr-comments/dry-run`.
10. Add GitHub error-shape fixtures for 403, 404, 422, and rate limit.
11. Add retry/backoff policy for live GitHub publish calls.
12. Add usage ledger meter for GitHub checks and PR comments.
13. Add hosted report link to PR comment body.
14. Add incident replay links to PR comment body.
15. Add waiver/approval status to PR comment body.
16. Add GitHub actor identity binding to review workflow records.
17. Add GitHub App installation readiness checks.
18. Add self-host GitHub Enterprise API base URL docs and tests.
19. Add export-firewall scan surface for GitHub publish receipts.
20. Add Growth-Auditor score for PR Gate readiness in dashboard.
