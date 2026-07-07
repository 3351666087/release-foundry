# Round12 Private Output Parity Checklist

Scope: compare output path handling across Python `services/runner/api_probe.py`, Python `packages/sdk/ashr_clone/calibrate.py`, TypeScript `packages/ts/ashr-clone/src/probe.ts`, and TypeScript `packages/ts/ashr-clone/src/calibrate.ts`.

Boundary:
- No Ashr API calls were made.
- No secrets, private key files, or raw private evidence files were read.
- This checklist is the only intended write for this Round12 pass.

## Current State

Python probe:
- Defaults output to `docs/evidence/private_refs/a1_api_<operation>_<dry_run|real>.json`.
- Accepts any user-provided `--output` path.
- `plan-batch` and `validate-gate` are local operations and still write records through the same output path machinery.
- No `--allow-nonprivate-output` flag exists.
- No output-root guard exists before API client construction.

Python calibrate:
- Defaults manifest output to `docs/evidence/private_refs/a1_python_api_calibration_manifest_<dry_run|real>.json`.
- Derives every per-step record path from the manifest directory via `step_output_path(...)`.
- Manifest states `raw_records_private=true`, but a user-provided public `--output` path moves both the manifest and per-step records beside that public path.
- No `--allow-nonprivate-output` flag exists.
- No output-root guard exists before client construction or step execution.

TypeScript probe:
- Defaults output to `docs/evidence/private_refs/a1_ts_api_<operation>_<dry_run|real>.json`.
- Accepts any user-provided `--output` path.
- Supports `--output -`, which skips file writing and can print full records when paired with `--print-record`.
- `plan-batch` and `validate-gate` are local operations and still use the same output path machinery.
- No `--allow-nonprivate-output` flag exists.
- No output-root guard exists before `AshrApiClient.fromEnv(...)`.

TypeScript calibrate:
- Defaults manifest output to `docs/evidence/private_refs/a1_ts_api_calibration_manifest_<dry_run|real>.json`.
- Derives every per-step record path from the manifest directory via `stepOutputPath(...)`.
- Manifest states `raw_records_private=true`, but a user-provided public `--output` path moves both the manifest and per-step records beside that public path.
- No `--allow-nonprivate-output` flag exists.
- No output-root guard exists before `AshrApiClient.fromEnv(...)`.

## Required Flag

Add the same flag to all four CLI surfaces:

`--allow-nonprivate-output`

Meaning:
- Default is false.
- When false, protected operations must write full records only under the resolved repository path `docs/evidence/private_refs`.
- When false, protected operations must reject stdout/no-file full-record sinks such as TypeScript probe `--output -`.
- When true, the command may write or print full evidence records outside `docs/evidence/private_refs`.
- The flag does not weaken redaction, quota-gate, paid-media, retry, mutation, or API-key guards.
- The flag must be represented in emitted evidence metadata when a command proceeds with nonprivate output.

Recommended emitted metadata:
- Probe records: `request.output_policy`.
- Calibration manifests: `guardrails.output_policy`.
- Fields: `private_output_required`, `private_root`, `output_path`, `output_is_private`, `nonprivate_output_override_used`, and `nonprivate_output_sinks`.
- `nonprivate_output_sinks` should include `file` for a path outside private refs, `stdout_record` for `--print-record`, and `stdout_record_no_file` for TypeScript probe `--output - --print-record`.

## Private Path Definition

The private root is the repository-local directory:

`docs/evidence/private_refs`

Path rules:
- Resolve the output path to an absolute path before comparison.
- Resolve the private root to an absolute path before comparison.
- A file output is private only when the resolved output path is inside the resolved private root.
- A path equal to the private root directory itself is invalid because output must be a file.
- Path traversal must be blocked by resolution. For example, `docs/evidence/private_refs/../public.json` is nonprivate.
- Prefix lookalikes must be blocked. For example, `docs/evidence/private_refs_evil/out.json` is nonprivate.
- Relative paths and absolute paths are both allowed only if their resolved target is private, unless `--allow-nonprivate-output` is present.

## Protected Operations

Python probe and TypeScript probe:
- Protected by default: every operation that can emit an `AshrApiCallRecord`.
- This includes local `plan-batch` and `validate-gate`.
- This includes dry-run read operations because their records can capture request parameters, response shapes, output paths, and calibration metadata.
- This includes real read operations, polling operations, and all mutating operations.
- `--help` is not protected because it emits usage text only.

Python calibrate and TypeScript calibrate:
- Protected by default: every calibration mode.
- This includes dry-run read-only calibration.
- This includes real read-only calibration.
- This includes mutating calibration.
- This includes `--print-record`, because it emits the manifest to stdout and the manifest points to per-step private records.
- `--help` is not protected because it emits usage text only.

Stdout handling:
- A one-line summary is allowed without `--allow-nonprivate-output` because it does not emit the full record.
- Full JSON record or manifest printing through `--print-record` is a nonprivate sink and requires `--allow-nonprivate-output`.
- TypeScript probe `--output -` is a nonprivate sink even without `--print-record`, because it suppresses private file persistence for a protected evidence record. It must require `--allow-nonprivate-output`.

## Expected Error Ordering

All four CLIs should use this ordering:

1. Parse syntax, option type, and help handling.
2. Resolve default or explicit output target.
3. Enforce private-output policy.
4. Run local non-file safety guards.
5. Read request/result/quota files only after the output policy passes.
6. Validate quota gates only after the output policy passes.
7. Construct SDK clients or read API-key environment only after the output policy passes.
8. Call transport/API only after all guards pass.

Required ordering examples:
- `--help` returns usage without output-policy checks.
- Unknown option or invalid integer fails before output-policy checks.
- Nonprivate `--output` fails before missing API key.
- Nonprivate `--output` fails before `--allow-mutate` / `--small-batch` / `--max-retries 0` errors.
- Nonprivate `--output` fails before reading `--request-file`, `--result-file`, `--quota-record`, or `--quota-gate-record`.
- Nonprivate `--output` fails before `AshrApiClient.from_env(...)` or `AshrApiClient.fromEnv(...)`.
- With `--allow-nonprivate-output`, normal guard ordering resumes: mutate guards, retry guards, quota-gate validation, key lookup, then transport.

## Exact Surface Requirements

Python probe:
- Add `--allow-nonprivate-output`.
- Guard `output = Path(args.output) if args.output else default_output_path(...)` immediately after parsing and before local operation handling, mutation guards, quota gate reads, and client construction.
- Reject explicit nonprivate file outputs without the flag.
- If Python adds `--output -` parity later, treat it like TypeScript probe and require `--allow-nonprivate-output`.
- Include output-policy metadata in every emitted record.

TypeScript probe:
- Add `allowNonprivateOutput` to `ProbeCliArgs` and parse `--allow-nonprivate-output`.
- Guard `outputPath = args.output === "-" ? undefined : ...` immediately after parsing.
- Reject `--output -` unless `--allow-nonprivate-output` is present.
- Reject any resolved file path outside `docs/evidence/private_refs` unless `--allow-nonprivate-output` is present.
- Reject `--print-record` unless `--allow-nonprivate-output` is present.
- Ensure the guard runs before `runLocalOperation(...)`, `validateExecuteGuards(...)`, and `AshrApiClient.fromEnv(...)`.
- Include output-policy metadata in every emitted record and error record.

Python calibrate:
- Add `allow_nonprivate_output` to `CalibrationArgs` and parse `--allow-nonprivate-output`.
- Guard the manifest output path before `validate_calibration_guards(...)` reads quota-gate files or `run_calibration(...)` constructs a client.
- Because step records are placed next to the manifest, the manifest path alone determines whether the full calibration output set is private.
- Reject `--print-record` unless `--allow-nonprivate-output` is present.
- Include output-policy metadata in the manifest guardrails.

TypeScript calibrate:
- Add `allowNonprivateOutput` to `CalibrationArgs` and parse `--allow-nonprivate-output`.
- Guard `const outputPath = args.output ?? defaultOutputPath(args.execute)` before `validateCalibrationGuards(args)` and before `runCalibration(...)`.
- Because step records are placed next to the manifest, the manifest path alone determines whether the full calibration output set is private.
- Reject `--print-record` unless `--allow-nonprivate-output` is present.
- Include output-policy metadata in the manifest guardrails.

## Required Test Cases

Use only synthetic fixtures and temp files. Do not read `docs/evidence/private_refs` contents and do not use real keys.

Shared path tests:
- Default output path is accepted without `--allow-nonprivate-output`.
- Explicit output inside resolved `docs/evidence/private_refs` is accepted without the flag.
- Explicit output outside `docs/evidence/private_refs` is rejected without the flag.
- Explicit output outside `docs/evidence/private_refs` is accepted with `--allow-nonprivate-output`.
- `docs/evidence/private_refs/../public.json` is rejected without the flag.
- `docs/evidence/private_refs_evil/out.json` is rejected without the flag.
- Absolute path inside the private root is accepted.
- Absolute path outside the private root is rejected without the flag.
- A path resolving to the private root directory itself is rejected.

Python probe tests:
- `plan-batch --output <nonprivate>` fails before reading a missing `--request-file`.
- `validate-gate --output <nonprivate>` fails before reading a missing `--quota-gate-record`.
- `health-check --execute --output <nonprivate>` fails before missing-key text is printed.
- `create-run --execute --output <nonprivate>` fails before `--allow-mutate` and before key lookup.
- `create-request --execute --allow-mutate --max-retries 0 --output <nonprivate> --quota-gate-record <synthetic>` fails on output policy before reading the gate file.
- With `--allow-nonprivate-output`, a dry-run `plan-batch` writes the nonprivate output and includes `request.output_policy.nonprivate_output_override_used=true`.

TypeScript probe tests:
- Same probe cases as Python.
- `--output -` fails without `--allow-nonprivate-output`.
- `--output - --allow-nonprivate-output --print-record` succeeds for a local dry-run operation and prints the full record.
- `--print-record` with a normal private file output fails without `--allow-nonprivate-output` because stdout receives the full record.
- Error records written after an allowed nonprivate output failure include output-policy metadata.

Python calibrate tests:
- Default dry-run calibration output is accepted without the flag and remains under private refs.
- `--output <nonprivate>` fails before client construction and before reading env keys.
- `--output <nonprivate> --execute` fails on output policy before `--small-batch` is reported.
- `--output <nonprivate> --execute --small-batch --max-retries 0 --include-mutating --quota-gate-record <synthetic>` fails before reading the gate file.
- `--print-record` fails without `--allow-nonprivate-output`.
- With `--allow-nonprivate-output`, dry-run calibration writes the manifest and step records beside the manifest and includes `guardrails.output_policy.nonprivate_output_override_used=true`.

TypeScript calibrate tests:
- Same calibrate cases as Python.
- Patch `AshrApiClient.fromEnv` or provide an empty env and assert nonprivate output errors do not mention `ASHR_API_KEY` or `ASHR_LABS_API_KEY`.
- Assert no step files are created when output policy fails.
- Assert step files are created beside an allowed nonprivate manifest only when `--allow-nonprivate-output` is present.

No-secret / no-private tests:
- Use synthetic request, result, quota, and gate files under test temp directories.
- Never read committed or ignored private evidence.
- Assert raw marker strings from synthetic request payloads do not appear in public-safe plan or manifest summaries unless the command is explicitly run with `--allow-nonprivate-output` and the test intentionally checks an output file under a temp directory.
- Assert stderr for output-policy failures does not include API env variable hints.

## Acceptance Criteria

The parity task is complete when:
- All four CLIs support `--allow-nonprivate-output`.
- All four CLIs reject nonprivate full-record outputs by default.
- Probe and calibrate use the same resolved-private-root definition.
- Calibrate protects both manifest and per-step record placement through the manifest path.
- TypeScript probe treats `--output -` and `--print-record` as nonprivate full-record sinks.
- Output-policy errors happen before key lookup, private input reads, quota-gate reads, client construction, and transport/API calls.
- Tests cover Python and TypeScript behavior without real API calls, secrets, private key files, or raw private evidence.
