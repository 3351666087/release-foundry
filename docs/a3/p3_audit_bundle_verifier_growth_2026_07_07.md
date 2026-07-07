# A3 Audit Bundle Verifier Growth - 2026-07-07

## Goal

Add the missing verification step after the audit bundle index/root hash work.

Beginner explanation:

- The previous pass created an audit bundle index.
- That index says: these files, hashes, waiver, approval, and custody events belong to this release.
- This pass adds the checker.
- The checker reads the bundle index and confirms whether the evidence still matches.

In plain language: A3 can now say not only "here is the evidence package," but also "I verified this evidence package has not been changed."

## Added Capability

A3 Gate CLI now supports:

```text
--verify-index <path>
```

Example command:

```text
node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --json
```

The verification output schema is:

```text
a3.audit_bundle_verification.v1
```

It checks:

- bundle schema version
- bundle root hash
- each bundle artifact SHA-256
- each bundle artifact byte size
- missing artifact files
- unsafe local paths
- chain-of-custody event hashes
- `previous_event_hash` links

## Why This Matters Commercially

An enterprise buyer does not only need a report. They need proof that the report and evidence still match the signed-off release.

This verifier makes A3 stronger for:

- release sign-off
- compliance review
- incident replay
- customer audit requests
- self-hosted evidence retention
- future GitHub artifact downloads

The sellable message is:

> A3 can generate a blocked-release evidence bundle and later verify that the bundle was not tampered with.

## Code Changes

- Added `verifyAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added `renderBundleVerificationMarkdown()` for human-readable verification output.
- Added CLI mode:
  - `--verify-index`
- Added verification output support:
  - stdout JSON/Markdown
  - `--output-json`
  - `--output-md`
- Verification mode does not require `--runs` or `--grades`.
- Verification honors strict/non-fail exit behavior:
  - strict mode exits nonzero on failed verification
  - no-fail mode can write failed evidence without breaking local generation

## Fixture

Added redacted verification fixture:

```text
fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json
```

The fixture confirms:

- schema: `a3.audit_bundle_verification.v1`
- status: `passed`
- root hash passed
- artifact hashes passed
- custody event hashes passed
- no local user paths

## Tests

Added tests in:

```text
tests/a3/a3_gate_cli.test.mjs
```

New coverage:

- committed bundle verifies successfully
- Markdown verification report renders
- tampered artifact hash fails verification
- root hash mismatch is detected
- CLI `--verify-index` writes JSON and Markdown verification reports
- committed verification fixture stays redacted

## Verification

Focused command:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result after this pass:

```text
tests 20
pass 20
fail 0
```

## Safety

- No live Ashr API call was made in this pass.
- No live GitHub API call was made.
- No `.env.local` read or write was needed.
- No API key, cookie, token, email, or signed media URL was saved.
- Verification output redaction still applies.

## Remaining Gaps

Still not done:

- verify a zipped/sealed bundle directory
- package immutable archive
- upload bundle as a GitHub Actions artifact
- sign bundle root hash with real identity
- bind approval to SSO/GitHub/OIDC identity
- persist bundle in durable self-host storage
- show verifier status in the dashboard UI

## Current Interpretation

This is a meaningful step toward commercial-grade auditability.

Before:

- A3 generated evidence.
- A3 generated hashes.
- But a customer had no simple command to verify the package later.

Now:

- A3 can verify the bundle index.
- A3 can detect tampering.
- A3 can produce machine-readable and human-readable verification reports.

That moves A3 closer to enterprise release governance instead of just eval reporting.
