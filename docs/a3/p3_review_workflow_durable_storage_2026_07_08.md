# P3 Durable Review Workflow Storage

Date: 2026-07-08

## Goal

Close the next A3 enterprise-release gap: file-backed waiver and approval validation now has an API and durable storage path. A3 can record waiver and approval evidence as hash-sealed review workflow records without changing A1 runner logic or A2 judge semantics.

## What changed

- Added review workflow schema:
  - `a3.review_workflow_record.v1`
  - `a3.review_workflow_index.v1`
  - `a3.review_workflow_receipt.v1`
- Added API routes:
  - `POST /api/a3/review/waivers`
  - `POST /api/a3/review/approvals`
  - `GET /api/a3/review/workflow`
- Added SQL migration table:
  - `review_workflow_records`
- Added SQLite persistence for review workflow records.
- Added dashboard durable review records section under Reviewer Workflow.
- Added JSON export summary:
  - `review_workflow`
- Added tests for service, store, API server, SQLite persistence, dashboard wiring, and report export.

## Validation reuse

The durable workflow reuses the existing file-backed validators:

- `validateWaiverRequest(...)`
- `validateApprovalRecord(...)`

That means durable API records use the same release gate, waiver policy, signer role, waiver binding, artifact hash, and separation-of-duties checks already proven by the Gate CLI tests.

## Safety model

- No real Ashr cloud mutation is performed.
- No `.env.local` is read.
- No real key, token, cookie, email, or live signed URL is committed.
- Raw signatures are not stored.
- Payload and review bodies are hash-sealed with SHA-256.
- Review workflow records are tenant/project scoped.
- A valid waiver or approval is evidence only; it does not automatically unblock a release.

## Commercial value

This moves A3 closer to an enterprise release sign-off product:

- Reviewers can submit waiver/approval evidence through an API.
- Release owners can prove which evidence was reviewed.
- Auditors can inspect durable rows rather than loose files.
- A future hosted version has a clear database table for retention, legal hold, signed approvals, and compliance review.

## Verification

Focused verification passed:

```text
node --test tests/a3/a3_review_workflow.test.mjs tests/a3/a3_store.test.mjs
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

## Remaining gaps

- Real cryptographic signature verification is still future work.
- Real reviewer identity binding through SSO/OIDC/GitHub is still future work.
- A live GitHub required check is still future work.
- Immutable archive storage and archive verifier are still future work.
