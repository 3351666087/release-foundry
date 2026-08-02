# A3 P3 Export Firewall CI Scan - 2026-07-07

## Goal

Add a CI-style guard that scans committed A3 generated/export artifacts for unredacted secret-like values and local account paths.

This pass is intentionally limited to test and evidence documentation. It does not edit dashboard, service, or app runtime files.

## What Is Scanned

Test entry point:

- `tests/a3/export_firewall_generated_artifacts.test.mjs`

Artifact roots:

- `docs/a3`
- `fixtures/a3`

Text artifact extensions:

- `.json`
- `.md`
- `.yml`
- `.yaml`
- `.txt`
- `.csv`
- `.html`

Current scan size: 140 text artifacts.

The scan includes generated A3 report evidence such as:

- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_report.redacted.md`
- `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- A3 P3 evidence docs under `docs/a3`

## What Is Not Scanned

The scanner deliberately skips:

- binary screenshot/image/media/archive-style extensions, including `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.pdf`, `.zip`, `.gz`, `.tar`, and `.whl`
- `.env`-style files
- `private_refs` paths
- screenshot directories

This keeps the CI check focused on exportable text artifacts and avoids reading local secret stores or binary screenshot evidence.

## Leak Patterns Checked

The test uses high-confidence regex checks aligned with the existing A3 export redaction firewall policy:

- API key assignments such as ReleaseFoundry/OpenAI/GitHub token variables with real-looking values
- generic secret/token/session assignments
- Authorization and Bearer token values
- Cookie and Set-Cookie headers
- common prefixed secret tokens
- signed media URLs with provider signature/token/expiry query markers
- raw email addresses
- Windows and macOS user-home paths

Failure output reports only `file:line:column` plus the pattern id. It does not print the matching secret-like text into CI logs.

## Allowlist Rationale

The only intentional allowlist is for `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md`.

Reason: that document is itself a redaction/firewall evidence map and contains literal examples such as placeholder cookie headers and user-home path patterns. The allowlist is line-fragment based and applies only to placeholder examples, not to the whole file. A real-looking value in that document would still fail the scan.

No fixture file is allowlisted.

## Command

```text
node --test tests/a3/export_firewall_generated_artifacts.test.mjs
```

## Verification Result

```text
tests 1
pass 1
fail 0
```

Focused run result on 2026-07-07:

```text
generated A3 docs and fixture report artifacts are free of unredacted secrets and account paths
```

## Next CI Step

Add this command to the A3 pull-request check after the existing A3 unit tests:

```text
node --test tests/a3/*.test.mjs
```

If CI time becomes a concern, keep this scanner as its own required job so export safety can fail fast before dashboard or integration checks run.
