# P3 Waiver Validation Growth Round - 2026-07-07

## Goal

Move A3 waiver support from policy text into a file-backed validation contract.

Before this round, A3 could say that a blocked release required an exceptional waiver. Now A3 can read a local `a3.waiver.v1` file, validate required fields, validate expiry, validate required approver roles, validate failed-check coverage, and emit an `a3.waiver_review.v1` result.

This is still not a live approval system. It is the local contract needed before approvals can become signed, persisted, and enforced in CI.

## 20 Growth Points Covered

1. Add `--waiver` to the Gate CLI.
2. Add `--generated-at` for deterministic waiver expiry tests.
3. Add waiver input file hashing to the CLI audit manifest.
4. Add waiver review output schema: `a3.waiver_review.v1`.
5. Add waiver request fixture schema: `a3.waiver.v1`.
6. Validate waiver schema version.
7. Validate required policy fields.
8. Validate waiver run id scope.
9. Validate release version scope.
10. Validate environment scope.
11. Validate head SHA scope.
12. Validate expiry date format.
13. Reject expired waivers.
14. Reject waiver expiry beyond the policy max.
15. Validate required approver roles.
16. Validate individual approval records with role, name, and timestamp.
17. Validate waiver coverage for failed gate checks.
18. Validate reviewed artifact hashes are SHA-256 values.
19. Add Markdown report Waiver Review summary.
20. Add committed redacted waiver request and waiver review fixtures.

## What Landed

Code:

- `services/report/a3_gate_cli.mjs`
  - Adds `validateWaiverRequest()`.
  - Adds `--waiver`.
  - Adds `--generated-at`.
  - Adds `waiver_review` to Gate CLI JSON output.
  - Adds waiver file hash to `audit_manifest.artifacts`.
  - Adds Waiver Review section to the Markdown report.

Fixtures:

- `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`

Tests:

- `tests/a3/a3_gate_cli.test.mjs`
  - Validates a file-backed exceptional waiver.
  - Rejects expired or incomplete waiver evidence.
  - Verifies the committed waiver review fixture.
  - Confirms the Markdown report contains `## Waiver Review`.

## Current Waiver Result

The committed demo waiver is intentionally a blocked-release exceptional waiver:

- Gate decision: `block_release`
- Waiver review status: `valid_exceptional_waiver`
- Accepted by local waiver policy: yes
- Automatic unblock: no
- Expiry max: 1 day
- Missing approvers: none
- Missing failed checks: none
- Reviewed artifact count: 1

Important: a valid waiver is evidence, not an automatic pass. The release remains blocked unless a future live policy explicitly allows this waiver to change CI behavior.

## Verification

Focused test:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 12
pass 12
fail 0
```

## Commercial Value

This is a buyer-facing governance step.

Enterprise customers do not only ask, "Did the gate fail?" They ask:

- Who accepted the risk?
- Was that person allowed to accept it?
- What exact failed checks were waived?
- What evidence did they review?
- When does the exception expire?
- Is there a follow-up issue?
- Did the waiver secretly unblock production?

A3 can now answer those questions locally with structured evidence.

## Remaining Gaps

- Waiver records are still local JSON fixtures, not persisted database records.
- Approval signatures are not cryptographic.
- Reviewer identity is not connected to GitHub, SSO, or OIDC.
- Follow-up issue existence is not verified against GitHub/Jira.
- Valid waiver does not yet integrate into a live required-check decision.
- No immutable audit bundle or append-only chain-of-custody exists.

## Next Growth Points

1. Add `a3.approval.v1` signed approval schema.
2. Bind approval to generated artifact manifest hash.
3. Add waiver revocation status.
4. Add superseded waiver status.
5. Add follow-up issue validator.
6. Add reviewer identity source field.
7. Add separation-of-duties rule.
8. Add file-backed approval index.
9. Add immutable bundle root hash.
10. Add append-only chain-of-custody event log.
11. Add live GitHub required-check policy for waiver behavior.
12. Add branch-protection fixture.
13. Add GitHub App/OIDC identity design.
14. Add self-host waiver retention policy.
15. Add waiver expiry dashboard panel.
16. Add waiver summary to PR comment dry-run body.
17. Add audit bundle export containing waiver and review fixtures.
18. Add DLP fail-closed mode before accepting waiver artifacts.
19. Add production replay requirement before exceptional waiver.
20. Add management sign-off report section.
