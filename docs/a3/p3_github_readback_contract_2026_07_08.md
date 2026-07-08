# P3 GitHub Readback Contract

## Goal

This round moves A3 release evidence from "we generated or posted a GitHub artifact" toward "we can read GitHub back and prove what is currently there."

For a commercial release gate, a local receipt is not enough. A3 must distinguish:

- `generated`: local artifact exists, but nothing was posted.
- `posted`: publish API returned success, but the external state has not been rechecked.
- `readback_confirmed`: GitHub was queried and the current external object matches the expected evidence.
- `stale`: GitHub still has an object, but it points to the wrong SHA or body/hash.
- `missing`: GitHub readback succeeded, but the expected object was not found.
- `deleted`: GitHub reports the expected object no longer exists.
- `permission_denied`: GitHub could not be inspected with the provided permission.
- `failed`: another sanitized readback failure happened.

## Added Contracts

- `a3.github_check_readback_receipt.v1`
- `a3.github_pr_comment_readback_receipt.v1`
- `a3.github_required_check_proof.v1`

These contracts are implemented in:

- `services/report/a3_github_integration.mjs`

They are carried into release evidence v2 through:

- `services/report/report_builder.mjs`
- `services/report/a3_release_evidence.mjs`
- `services/report/a3_store.mjs`

## A1/A2 Calibration

A1 and A2 semantics were not changed.

A1 still owns run, trace, observation, and tool-call source evidence. A3 only links release evidence to those downstream counts.

A2 still owns scenario, judge, grade, score, pass/fail, and failure taxonomy semantics. A3 only packages the resulting release evidence for PR review.

## Safety Boundary

This round did not call live GitHub.

The tests use mocked `fetchImpl` responses. Runtime tokens are accepted only as in-memory options or environment variables and are never stored in fixtures, docs, or receipts.

Required-check proof stays `plan_only` unless branch-protection readback confirms the check exists. A plan can never claim `enforced=true`.

## Fixtures

Added redacted fixture examples:

- `fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json`
- `fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json`
- `fixtures/a3/p3/a3_github_required_check_proof_plan_only.redacted.json`

## Verification

Focused verification:

```text
node --check services/report/a3_github_integration.mjs
node --check services/report/a3_release_evidence.mjs
node --check services/report/report_builder.mjs
node --test tests/a3/a3_github_integration.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs
```

Result:

```text
40 pass
0 fail
```

## Remaining Gap

This is now live-capable, but not live-confirmed in this repository yet.

To reach production-grade enforcement, a maintainer must allow CI or a GitHub App to:

1. Publish the `Ashr++ Release Gate` check.
2. Publish or update the PR comment.
3. Configure branch protection to require the check.
4. Run readback after publish and store the readback receipt.
