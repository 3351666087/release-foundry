# A3 GitHub Publish Evidence Audit Bundle - 2026-07-08

## Purpose

A3 already produces local release-gate reports, GitHub Check payloads, PR-comment payloads, and dry-run publish receipts. This round makes those GitHub publish receipts auditable: the Gate CLI can now include them in the generated artifact manifest and audit bundle index with stable SHA-256 hashes.

In beginner terms: after A3 says "this release is blocked" and prepares GitHub evidence, the audit bundle can prove which exact files were part of that release packet.

## New Gate CLI Inputs

Optional inputs:

- `--github-check-publish-receipt`
- `--github-pr-comment-publish-receipt`
- `--github-required-check-plan`

Expected redacted fixtures:

- `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json`
- `fixtures/a3/p3/a3_github_required_check_plan.redacted.json`

## What Gets Recorded

For each provided GitHub evidence artifact, A3 records:

- artifact id
- workspace-relative path
- content type
- SHA-256
- byte size
- `origin: external_github_publish_evidence`

The CLI reads the files and hashes them. It does not rewrite the evidence files.

## A1/A2 Boundary

These GitHub files are A3 delivery evidence only.

- They are not A1 runner inputs.
- They are not A2 judge inputs.
- They do not change run, trace, tool-call, score, pass/fail, or failure-class semantics.

The release gate still uses A1/A2-derived data for the actual decision. GitHub publish evidence proves how A3 packaged and published that decision.

## Verification

Focused checks:

```text
node --check services/report/a3_gate_cli.mjs
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
21 tests
21 pass
0 fail
```

## Safety

- No real API key is read, printed, or committed.
- No live GitHub branch-protection mutation is performed.
- No real Ashr API call is needed for this feature.
- Required-check enforcement remains a redacted plan artifact until a maintainer explicitly approves live configuration.
