# P3 Signed Approval Validation Growth Round - 2026-07-07

## Goal

Move A3 from "waiver evidence exists" to "structured sign-off evidence exists."

Before this round, A3 could validate a local waiver file. Now A3 can also validate a local `a3.approval.v1` approval record and emit an `a3.approval_review.v1` result.

This is still not cryptographic signing or durable backend persistence. It is the local contract required before approvals can be tied to GitHub actors, OIDC, SSO, immutable bundles, or live required checks.

## 20 Growth Points Covered

1. Add `--approval` to the Gate CLI.
2. Add approval input file hashing to the audit manifest.
3. Add approval record schema: `a3.approval.v1`.
4. Add approval review schema: `a3.approval_review.v1`.
5. Validate approval schema version.
6. Validate approval id.
7. Validate decision enum.
8. Block normal `approve_release` decisions for blocked releases.
9. Require `approve_exception` for non-approved gate states.
10. Validate run id scope.
11. Validate release version scope.
12. Validate environment scope.
13. Validate head SHA scope.
14. Validate waiver id binding.
15. Validate signer role/name/timestamp.
16. Validate co-signer role/name/timestamp.
17. Validate required signer roles from release workflow.
18. Validate reviewed artifact SHA-256 hashes.
19. Validate separation-of-duties guardrail.
20. Add Markdown Approval Review summary.

## What Landed

Code:

- `services/report/a3_gate_cli.mjs`
  - Adds `validateApprovalRecord()`.
  - Adds `--approval`.
  - Adds `approval_review` to Gate CLI JSON output.
  - Adds approval file hash to `audit_manifest.artifacts`.
  - Adds Approval Review section to the Markdown report.

Fixtures:

- `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`

Tests:

- `tests/a3/a3_gate_cli.test.mjs`
  - Validates a file-backed exception approval.
  - Rejects too-permissive approval decisions.
  - Rejects missing required signer roles.
  - Rejects self-approval through separation-of-duties guardrail.
  - Verifies the committed approval review fixture.
  - Confirms the Markdown report contains `## Approval Review`.

## Current Approval Result

The committed demo approval represents an exception approval for a blocked release:

- Gate decision: `block_release`
- Approval decision: `approve_exception`
- Approval review status: `valid_exception_approval`
- Accepted by local approval policy: yes
- Automatic unblock: no
- Signer role: `Release owner`
- Co-signer count: 3
- Missing required signer roles: none
- Reviewed artifact count: 2

Important: approval evidence records sign-off, but this local contract does not change the gate exit behavior.

## Verification

Focused test:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 15
pass 15
fail 0
```

## Commercial Value

This makes A3 more credible as an enterprise release-control product.

Customers do not only need "the release failed" or "someone wrote a waiver." They need an audit answer to:

- Who signed this decision?
- Was the signer in the required reviewer lane?
- Did the approval match the exact run, release, environment, and head SHA?
- Did the approval reference the waiver?
- What artifacts did the signer review?
- Was self-approval blocked?
- Did this approval automatically override the gate?

A3 can now answer those questions locally with structured evidence.

## Remaining Gaps

- Signatures are file-backed demo records, not cryptographic signatures.
- Signer identity is not connected to GitHub actor, OIDC, SSO, or RBAC.
- Approval records are not stored in a durable backend.
- Approval does not yet change a live GitHub required check.
- There is no immutable audit bundle root hash.
- Follow-up issue existence is not verified.

## Next Growth Points

1. Add cryptographic signature field.
2. Add signer public key fingerprint.
3. Add GitHub actor identity binding.
4. Add OIDC subject binding.
5. Add SSO/RBAC role binding.
6. Add approval revocation.
7. Add approval superseded status.
8. Add approval expiry.
9. Add approval index file.
10. Add immutable audit bundle root hash.
11. Add chain-of-custody event log.
12. Add follow-up issue validator.
13. Add live GitHub required-check policy for valid exception approval.
14. Add branch protection fixture.
15. Add dashboard Approval Review panel.
16. Add PR comment Approval Review summary.
17. Add management sign-off packet export.
18. Add self-host retention policy.
19. Add API schema docs for approvals.
20. Add replay-before-approval policy.
