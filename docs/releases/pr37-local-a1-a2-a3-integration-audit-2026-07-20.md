# PR #37 Local A1/A2/A3 Integration Audit — 2026-07-20

## Scope

- Repository: `3351666087/release-foundry`
- Pull request: `#37`
- Integration branch: `agent/enterprise-release-integration`
- Isolated worktree:
  `C:\Users\33516\Documents\ReleaseFoundry_pr37_audit_20260720`
- Remote integration baseline:
  `84d857ef5a1ec9d5280ab312e857e76b7ea5c848`
- Audited pre-fix integration HEAD:
  `349836741ca7d75d1ef2976dc2840c133c0f4e46`

All changes and release checks in this audit were performed in the isolated
worktree. The original `C:\Users\33516\Documents\ReleaseFoundry` worktree was not reset,
cleaned, or used for integration edits.

## Integration commits already ahead of the remote PR branch

```text
34983674 A3: redesign dashboard and hosted report frontend visuals
8f928751 fix(a1): align identity SDK parity and journal tests
fa0a7b4b feat(a1): add canonical identity client parity
3a941469 fix(ci): restore immutable rc.1 release evidence
```

## Local branch and commit coverage

### Main

- `origin/main`:
  `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- local `main`:
  `7401a9ef59730d3bc40f025a79fd87e3c40dc696`
- `git log --no-merges HEAD..main` returned no commits.

The local `main` merge history contains no unique non-merge content that still
needs to be moved into the integration branch.

### A1

Local `agent/a1-local-sdk-runner` was at
`3549b781adbba972304dbd15e362aefb28e290e1`.

Its two reviewed commits were:

```text
3549b781 feat(a1): add canonical identity client parity
e8310d2f A1: add audit log and release evidence parity
```

`e8310d2f` is patch-equivalent to integrated work. `3549b781` is not an exact
patch-ID match because it was ported as `fa0a7b4b` and then corrected by
`8f928751` for SDK parity and journal tests. Reapplying the original commit
would duplicate and regress the integrated resolution.

Local `agent/a1-local-sdk-runner-clean` at `6ca7327a` is also
patch-equivalent to integrated work.

### A2

The reviewed A2 publication/strategy refs and their relevant commits are
ancestors of the integration HEAD:

```text
agent/a1-round54-publish
agent/a1-sync-publish
agent/a2-strategy-provider-independent
agent/tmp-g3-a2-merge-scenario-20260710

51a1d70b
cc42eda3
97141b4b
10ccee31
5922974a
9d1f5b80
f55c8baa
98b0075a
7fa2829c
ca4206db
```

No additional A2 commit from those local refs needs to be transplanted.

### A3

`backup/a3-dashboard-local-4fb555f` at `4fb555f8` is not an exact patch-ID
match because its dashboard work was conflict-resolved and adapted to the
combined A1/A2/A3 tree as:

```text
34983674 A3: redesign dashboard and hosted report frontend visuals
```

The detached merge commit
`c2716245e9be35d24e2a0b9b56a52ba5e285cb99` has parents
`989fdc3606a2427eec4216196fa0d1f34924c8b9b` and
`c29854d6605366b13f086c96756ca85956517bcb`. Both parents are ancestors of
the integration HEAD, and `git log --no-merges HEAD..c2716245` returned no
unique non-merge content.

## Completeness corrections

The final local review found and corrected the following release-gate issues:

1. Removed a literal trailing `\n` sequence from the A1 round-38 JSON evidence
   so every tracked JSON document parses normally.
2. Updated the A2 cross-lane security-context totals from 88 to 98 routes and
   from 87 to 97 intentional differences.
3. Changed the Ollama multimodal deadline calculation to integer monotonic
   nanoseconds and made sub-millisecond provider budgets fail closed.
4. Made the installer-path test skip when `D:` is absent or has less than
   20 GiB free, instead of reporting an environmental filesystem limitation
   as a product failure.
5. Added an immutable RC.2 copy of the trusted A2 spine handoff and regenerated
   the dependent A3 gate, archive, deployment, and release evidence chain.

The new immutable file is:

```text
fixtures/a3/golden-path/rc2/a2_trusted_spine_handoff.snapshot.json
SHA256 bfc30d38dea81f68daf18c4a43061c70b310183e130a4677a40a7f932cc86949
size   6186 bytes
```

The ten regenerated RC.2 evidence files matched an independent repository-
external regeneration byte for byte.

## RC.1 and RC.2 evidence verification

All six strict verification commands exited with status 0 and reported
`status: passed`:

```text
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/golden-path/audit-bundle-index.json --generated-at 2026-07-12T11:40:01.000Z --strict-exit --json
node services/report/a3_audit_archive.mjs --verify fixtures/a3/golden-path/audit-archive-manifest.json --generated-at 2026-07-12T11:40:03.000Z --json
node services/report/a3_release_delivery_cli.mjs --verify-manifest fixtures/a3/golden-path/release-artifact-manifest.json --verified-at 2026-07-12T11:40:05.000Z --strict-exit --json

node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/golden-path/rc2/audit-bundle-index.json --generated-at 2026-07-12T14:02:01.000Z --strict-exit --json
node services/report/a3_audit_archive.mjs --verify fixtures/a3/golden-path/rc2/audit-archive-manifest.json --generated-at 2026-07-12T14:02:03.000Z --json
node services/report/a3_release_delivery_cli.mjs --verify-manifest fixtures/a3/golden-path/rc2/release-artifact-manifest.json --verified-at 2026-07-12T14:02:06.000Z --strict-exit --json
```

Current RC.2 roots:

```text
bundle root:
04e34b9c52e9183564fcf9bfeb52d73b455cca73ec04a6242570c172d8c4d2c1

archive root:
78a259521bc9d264a7a4da523f1d4fae0448a46ddd5680205b5c869303ac6d20

release manifest hash:
04ba2da57fed18f3fcd3456b63cd4f1d19aa67f14f4ae8046a05867f0684a6cd
```

RC.2 continues to report `status: blocked_by_a2` and
`production_ready: false`. That is the preserved historical A2 Decision
Ledger result, not a verifier failure. This integration does not rewrite the
A2 authority to manufacture a production-ready result.

## Local gate results

### Python

```text
A1/A2/integration: 2050 passed, 56 skipped, 19 warnings
Release:             10 passed
A2 targeted:          4 passed, 1 skipped
```

Live PostgreSQL variables were not configured. PostgreSQL/live-provider cases
were therefore skipped or not executed and are not represented as passing
live tests.

### A3 and web

```text
A3 Node: 520 tests, 519 passed, 1 skipped, 0 failed
Playwright: 21 passed
apps/webapp npm ci: passed
apps/webapp check/typecheck/build: passed
root npm ci: passed
```

### SDK and language gates

```text
releasefoundry: 650 passed
Go releasefoundry: passed
Go integration: passed
Rust: all suites passed
gofmt: passed
go mod verify: passed
cargo metadata --no-deps --format-version 1: passed
```

### Static, repository, and release-policy checks

```text
git fsck --full --no-dangling: passed
tracked file readability: 2432 files
JSON parse: 722 files, errors=0
python scripts/cl_guard.py hygiene: findings=[]
python scripts/cl_guard.py commercial: blockers=0, advisories=0
git diff --check: passed
python scripts/cl_guard.py plan --base origin/main --head HEAD:
  DIFF_HIGH_CONFIDENCE_COUNT=0
python scripts/a2_regenerate_fixtures.py --check:
  all 56 generated fixture files match committed output
npm ci/build packages/ts/releasefoundry: passed
python -m compileall packages services scripts tests: passed
```

Generated calibration fixtures and Playwright screenshots created as test
side effects were restored before preparing the release changes.

## Environment audit

The name-only environment audit is recorded in
`docs/security/environment-variable-audit-2026-07-20.md`.

It covers 169 referenced names, identifies 41 conservatively secret-likely
names, and records only presence state. Five referenced variables were present
in the current process. No value is included in Git.

## GitHub completion status

At the time this local audit was written:

- the final local diff, policy gates, and regenerated A2 fixtures had passed
  their last pre-commit checks;
- the audit/fix commits had not yet been pushed;
- PR #37 had not yet been evaluated against the new pushed HEAD;
- merge, long-lived A1/A2/A3 branch synchronization, and remote integration
  branch deletion remained pending.

These GitHub operations must be confirmed from the actual post-push state and
must not be inferred from earlier checks.
