# A3 Audit Bundle Index Growth - 2026-07-07

## Goal

Move A3 from separate release-gate files toward one sealed audit evidence package that an enterprise reviewer can verify later.

Beginner explanation:

- Before this pass, A3 could produce several useful files: gate JSON, Markdown report, GitHub check payload, PR comment, waiver review, approval review, and generated artifact manifest.
- The gap was that those files were still separate pieces.
- This pass adds an audit bundle index, which is like a table of contents for the whole release evidence package.
- The bundle index has a root hash, which is like a tamper-evident fingerprint for the evidence package.
- If any artifact hash, release decision, approval status, or custody event changes, the root hash changes.

## Added Capability

A3 Gate CLI now supports:

```text
--output-bundle <path>
```

The output schema is:

```text
a3.audit_bundle_index.v1
```

It records:

- bundle id
- release version
- run id
- environment
- owner
- gate decision
- risk score
- merge-blocking status
- waiver review status
- approval review status
- source input artifacts
- generated output artifacts
- governance records
- chain-of-custody events
- retention metadata
- verification command
- root hash

## Why This Matters Commercially

This makes A3 more like enterprise release governance, not just a dashboard.

A buyer can ask:

- What evidence blocked this agent release?
- Which exact files were reviewed?
- Was the waiver scoped to the same run and release?
- Was the approval scoped to the same release?
- Did anyone change the evidence after sign-off?
- Can we verify the package later during an audit?

The new audit bundle index gives A3 a concrete answer: verify the bundle root hash and artifact hashes.

## Code Changes

- Added `buildAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added `--output-bundle` CLI option.
- Added canonical JSON hashing for stable root hashes.
- Added bundle artifact normalization so paths stay workspace-relative or redacted as `[outside-workspace]/...`.
- Added chain-of-custody events with `previous_event_hash` and `event_hash`.
- Added input artifact `content_type` and `byte_size` metadata.

## Fixture

Added redacted fixture:

```text
fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json
```

This fixture describes a blocked local release with:

- source inputs: runs, grades, coverage, thresholds
- governance records: waiver and approval
- gate decision: `block_release`
- waiver status: `valid_exceptional_waiver`
- approval status: `valid_exception_approval`
- automatic unblock: `false`
- root hash: SHA-256

## Chain Of Custody

The initial local chain includes:

- `gate_built`
- `input_artifacts_hashed`
- `generated_artifacts_hashed` when output files are generated
- `waiver_reviewed` when a waiver is supplied
- `approval_reviewed` when an approval is supplied
- `bundle_index_written`

Each event has its own hash and points to the previous event hash.

## Tests

Added coverage in `tests/a3/a3_gate_cli.test.mjs` for:

- stable bundle root hash
- self-hash exclusion
- waiver and approval artifact inclusion
- generated manifest inclusion when CLI writes output artifacts
- workspace-relative/safe paths
- chain-of-custody event hashes
- committed bundle fixture shape

## Verification

Focused command:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_releasefoundry_mapper.test.mjs
```

## Safety

- No live ReleaseFoundry API call was made in this pass.
- No live GitHub API call was made.
- No `.env.local` read or write was needed.
- No API key, cookie, token, email, or signed media URL was saved.
- Bundle paths avoid local absolute user directories.

## Remaining Gaps

This is still a local audit bundle index, not the final enterprise storage system.

Still missing:

- `releasefoundry gate verify --index`
- immutable zip/archive packaging
- generated PDF and screenshot hashing
- durable storage
- cryptographic signer identity
- GitHub artifact upload
- live required GitHub check
- self-host retention backend

## Current Interpretation

A3 now has a stronger enterprise story:

> A3 does not only say whether an agent release should be blocked. It can also produce a sealed, hashed index of the evidence behind that decision.

That is closer to something a team can use for release sign-off, audit review, and future compliance workflows.
