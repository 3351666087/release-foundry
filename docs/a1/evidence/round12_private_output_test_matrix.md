# Round12 Private Output Enforcement Test Matrix

Scope: reviewer-only matrix for private output enforcement across:

- `services/runner/api_probe.py`
- `packages/sdk/ashr_clone/calibrate.py`
- `packages/ts/ashr-clone/src/probe.ts`
- `packages/ts/ashr-clone/src/calibrate.ts`

No secrets, private key files, raw private evidence, or API calls are required for these tests. Use synthetic temp files only.

## Current Risk Summary

The four surfaces default to `docs/evidence/private_refs`, but custom `--output` paths are accepted and writer helpers create parent directories without an owned-private-output check. The calibrators also derive per-step record paths from the manifest output directory, so one unsafe manifest path fans out into multiple private record files. TS probe supports `--output -`, while the calibrators and Python probe do not appear to have an equivalent explicit no-file mode.

## High-Risk Failure Paths

1. Explicit `--output` writes private real-call records into tracked/public docs paths.
2. Absolute paths outside the repo or outside `docs/evidence/private_refs` are accepted.
3. Relative traversal such as `docs/evidence/private_refs/../public.json` escapes the private directory after resolution.
4. Windows path variants, drive-qualified paths, mixed separators, and case changes bypass simple prefix checks.
5. Calibrator manifest output outside private refs causes per-step files to be written beside that unsafe manifest.
6. Error-record paths use the same unsafe output path after a guard/auth/client error.
7. Local `plan-batch` and `validate-gate` are treated as harmless and allowed to write public paths even though they may carry quota-gate and private path metadata.
8. `--print-record` emits full private manifests or records to stdout during real/small-batch execution.
9. `--output -` behavior is inconsistent across Python/TS surfaces and may be mistaken for a safe no-write mode.
10. Enforcement added too bluntly could break tempdir unit tests, existing ignored private evidence workflows, or dry-run public examples.

## Enforcement Contract To Test

| Rule | Expected Behavior |
| --- | --- |
| Default output | Stays under `docs/evidence/private_refs` for all four surfaces. |
| Explicit private output | Relative or absolute paths resolving inside `docs/evidence/private_refs` are allowed. |
| Explicit public output | Paths resolving outside `docs/evidence/private_refs` are rejected before client/API-key lookup for real or private-producing commands. |
| Path traversal | Resolved absolute path, not raw string prefix, determines allow/deny. |
| Derived records | Calibrator per-step files inherit only from an already-approved manifest directory. |
| No-file mode | `--output -` is allowed only where intentionally supported and must not write error records either. |
| stdout | Full record printing is blocked or explicitly marked unsafe for real/private-producing commands. |
| Compatibility | Tests can still use temp dirs only through an explicit test-only/private-output override or by using `--output -` where supported. |

## Python Tests Needed

| ID | Surface | Scenario | Synthetic Inputs | Expected Result | Risk Covered |
| --- | --- | --- | --- | --- | --- |
| P12-01 | `services.runner.api_probe` | Default dry-run output path | `init` without `--output` | Summary output path starts with `docs/evidence/private_refs/a1_api_init_dry_run.json` | Default private convention |
| P12-02 | `services.runner.api_probe` | Reject public explicit output for real read-only | `health-check --execute --output docs/a1/evidence/leak.json`, env empty | Exit 2 before key lookup; no file created | Public-path leak before auth |
| P12-03 | `services.runner.api_probe` | Reject public explicit output for dry-run mutating plan | `create-request --request-file <synthetic> --output docs/a1/evidence/leak.json` | Exit 2 or documented allow only if dry-run public-safe policy says yes | Dry-run private-policy boundary |
| P12-04 | `services.runner.api_probe` | Allow explicit private output | `plan-batch --request-file <synthetic> --output docs/evidence/private_refs/round12_plan.json` | Exit 0; file written; redacted JSON only | Happy path |
| P12-05 | `services.runner.api_probe` | Reject traversal | `--output docs/evidence/private_refs/../round12_escape.json` | Exit 2; resolved path denied; no file | Prefix bypass |
| P12-06 | `services.runner.api_probe` | Reject absolute outside workspace/private refs | `--output C:\Users\33516\Documents\Ashr\docs\a1\evidence\leak.json` | Exit 2; no file | Windows absolute path |
| P12-07 | `services.runner.api_probe` | Error record does not write unsafe output | Missing key or invalid gate with public `--output` | No public error record is created | Error-path leak |
| P12-08 | `services.runner.api_probe` | Local validator output policy | `validate-gate --quota-gate-record <synthetic> --output docs/a1/evidence/leak.json` | Rejected unless local validation records are explicitly classified public-safe | Local-op metadata leak |
| P12-09 | Python SDK calibrator | Default manifest and step paths private | `CalibrationArgs(output=None)` dry-run with fake client | Manifest default and all `private_record_path` values under private refs | Calibrator default |
| P12-10 | Python SDK calibrator | Reject public manifest path | `--output docs/a1/evidence/calibration.json` | Exit/error before client construction; no manifest or step files | Fan-out leak |
| P12-11 | Python SDK calibrator | Reject traversal manifest path | `--output docs/evidence/private_refs/../calibration.json` | Exit/error; no manifest or step files | Resolved path enforcement |
| P12-12 | Python SDK calibrator | Allow private manifest path and derived step files | `--output docs/evidence/private_refs/round12_manifest.json` with fake client | Manifest and all step files under same approved private dir | Derived-file safety |
| P12-13 | Python SDK calibrator | Error step path remains private | Fake client raises; approved private manifest path | Error step file written only under private refs | Error fan-out |
| P12-14 | Python SDK calibrator | `--print-record` real/private output guard | Real/small-batch args with `--print-record`, fake client only | Either rejected or emits only safe summary by documented policy | Stdout leak |

## TypeScript Tests Needed

| ID | Surface | Scenario | Synthetic Inputs | Expected Result | Risk Covered |
| --- | --- | --- | --- | --- | --- |
| T12-01 | TS probe | Default output path private | `main(["init"], {}, capture)` | Summary output path starts with `docs/evidence/private_refs/a1_ts_api_init_dry_run.json` | Default private convention |
| T12-02 | TS probe | `--output -` writes no file | `health-check --output - --print-record` | Exit 0; JSON on stdout; no filesystem write | Intentional no-write mode |
| T12-03 | TS probe | Reject public explicit output for execute | `health-check --execute --output docs/a1/evidence/leak.json`, empty env | Exit 2 before key hint or before write; no file | Real read-only private output |
| T12-04 | TS probe | Reject public explicit output for local plan | `plan-batch --request-file <synthetic> --output docs/a1/evidence/leak.json` | Rejected unless policy explicitly marks plan records public-safe | Local planner metadata |
| T12-05 | TS probe | Allow private explicit output | `plan-batch --request-file <synthetic> --output docs/evidence/private_refs/round12_plan.json` | Exit 0; file written | Happy path |
| T12-06 | TS probe | Reject traversal | `--output docs/evidence/private_refs/../round12_escape.json` | Exit 2; no file | Prefix bypass |
| T12-07 | TS probe | Error record respects denied output | Invalid gate or missing key with public output | No public error record is written | Error-path leak |
| T12-08 | TS probe | `--print-record` real/private guard | Mutating execute with synthetic gate and `--print-record` | Rejected or stdout limited to summary by documented policy | Full JSON stdout leak |
| T12-09 | TS calibrator | Default manifest and step paths private | `main([])` with temp cwd or inspect manifest summary | Default output under private refs and step paths inherit private dir | Calibrator default |
| T12-10 | TS calibrator | Reject public manifest path | `--output docs/a1/evidence/calibration.json` | Exit 2; no manifest or step files | Fan-out leak |
| T12-11 | TS calibrator | Reject traversal manifest path | `--output docs/evidence/private_refs/../calibration.json` | Exit 2; no manifest or step files | Resolved path enforcement |
| T12-12 | TS calibrator | Allow private manifest path and derived steps | `--output docs/evidence/private_refs/round12_manifest.json` with dry-run/fake env | Manifest and all step files stay under private refs | Derived-file safety |
| T12-13 | TS calibrator | Error step path remains private | Fake/injected failure with approved private manifest | Error file written only under private refs | Error fan-out |
| T12-14 | TS calibrator | `--print-record` guard | Private-producing args with `--print-record` | Rejected or safe-summary-only by documented policy | Stdout leak |

## Cross-Surface Tests

| ID | Scenario | Expected Result |
| --- | --- | --- |
| X12-01 | Python and TS normalize private root the same way on Windows. | Same allow/deny result for `docs/evidence/private_refs/foo.json`, absolute private path, mixed separators, and case variants. |
| X12-02 | Python and TS deny the same traversal forms. | Same deny result for `../`, `private_refs/..`, repeated separators, and dot segments. |
| X12-03 | Python and TS preserve test ergonomics. | Unit tests can still write to temp dirs only via documented explicit test helper or no-file mode; production CLI denies temp/public output for private records. |
| X12-04 | Denied output fails before API/key lookup. | Missing API key text is not emitted when the first failure should be private-output policy. |
| X12-05 | Denied output fails before reading large/sensitive input payloads where possible. | For missing/denied output, request/result/quota files are not read unnecessarily. |

## Backwards Compatibility Risks

| Risk | Impact | Mitigation Test |
| --- | --- | --- |
| Existing unit tests write outputs to temp directories. | Private-root enforcement can break current tests even when using synthetic data. | Provide explicit test-only helper/API or use `--output -`; assert production CLI still denies temp dirs for private-producing commands. |
| Developers use custom ignored paths outside `docs/evidence/private_refs`. | Workflows may fail after enforcement. | Support an explicit `--allow-private-output-outside-default` style flag only for local/dev use, with loud audit metadata, or document migration. |
| Dry-run records may have been treated as public-safe. | Blocking all dry-run custom output could feel too strict. | Split tests by record class: public-safe dry-run summary vs private-producing full record, and document allowed cases. |
| `--output -` is TS probe-only. | Users may expect Python probe/calibrators to support no-write mode. | Add parity tests or document non-support; ensure unsupported `-` does not create a literal `-` file. |
| Calibrator step-output derivation changes. | Existing scripts that pass a manifest path and expect adjacent step files may break. | Test private manifest path still produces adjacent private step files; public manifest path denied before any step file writes. |
| `--print-record` restrictions change CLI output. | Existing debugging workflows may lose full JSON on stdout. | Provide safe summary mode and require explicit private-output path for full records. |
| Windows path normalization is subtle. | Prefix-only checks can be bypassed or deny valid paths. | Test resolved absolute paths, drive letters, mixed separators, dot segments, and case-insensitive matching. |

## Reviewer Acceptance Bar

- Every surface has at least one allow-private-output test and one deny-public-output test.
- Denied output paths are rejected before API-key lookup and before any file is created.
- Calibrator tests prove both manifest and all derived per-step records stay inside the approved private directory.
- Error-path tests prove rejected operations do not write public error records.
- TS probe `--output -` behavior is explicitly tested and not silently generalized to Python surfaces.
- Backwards compatibility behavior is documented for tempdir tests, dry-run public-safe records, and existing custom ignored paths.
