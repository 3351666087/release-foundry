# Round11 TS Probe Parity Checklist

Scope: compare Python `services/runner/api_probe.py` `plan-batch` / `validate-gate` behavior with current TypeScript `packages/ts/ashr-clone/src/probe.ts`.

Boundary:
- No Ashr API calls were made for this checklist.
- No private refs, key files, or environment secret values were opened or read.
- This file is the only intended write for the Round11 Explorer-SDK/API parity pass.

## Current Parity Verdict

Post-integration note: this checklist was written before the Round11 implementation landed. The core producer/validator gap it identifies is now closed in `packages/ts/ashr-clone/src/probe.ts` with tests in `packages/ts/ashr-clone/test/probe.test.mjs`; remaining items below are retained as follow-up coverage and drift-control requirements.

Pre-implementation verdict: TypeScript had partial quota-gate consumption parity, but not producer/validator CLI parity.

Python currently exposes first-class `plan-batch` and `validate-gate` operations. Those operations are planning/read-only only, avoid API client construction, write public-safe evidence records, and are covered by Python tests.

TypeScript currently validates existing `plan_batch` records during mutating `create-run` / `create-request --execute` guard checks, including TTL, target operation, create-request target binding, and quota evidence checks. It does not currently expose `plan-batch` or `validate-gate` as CLI operations, does not parse `--target-operation`, `--small-batch-size`, `--batch-size`, or `--quota-record`, and does not generate plan-batch evidence records itself.

## Python Contract To Match

`plan-batch` behavior:
- CLI accepts `plan-batch` as an operation and rejects `--execute`.
- CLI accepts `--target-operation`, defaulting to `create-request`.
- CLI accepts `--request-file` and optional `--request-schema-file` when `--target-operation create-request`.
- CLI accepts `--allow-media-generation`, `--allow-non-text-inputs`, `--max-request-variations`, `--small-batch-size`, `--batch-size`, and `--quota-record`.
- It does not construct `AshrApiClient` and does not require an API key.
- It writes a record with `schema_version=ashr.clone.api_probe_batch_plan.v1`, `function=plan_batch`, `dry_run=true`, `attempts=0`, `request.estimated_calls=0`, and `request.mutates=false`.
- Record status is `planned` only when `response.plan.quota_stop_go.decision == "go"`; otherwise it is `blocked`.
- `response.plan` includes `schema_version`, `target_operation`, `created_at`, `target_binding`, `phase_order`, `small_batch_size`, `batch_size`, `operation_mutates`, `preflight`, `modality_sequence`, `quota_stop_go`, `phases`, and `guardrails`.
- `target_binding` uses schema `ashr.clone.api_probe_target_binding.v1`, records request/schema fingerprints rather than raw payloads, includes `small_batch_size`, `batch_size`, modality order, and has `raw_request_not_recorded=true`.
- No quota record means `quota_stop_go.decision == "wait"` and both `can_enter_small_batch` / `can_enter_batch` are false.
- Quota-block evidence produces `decision == "stop"`.
- Retry/reset header evidence produces `decision == "wait"`.
- Quota or rate-limit evidence without a block/wait hint produces `decision == "go"`.

`create-request` dry-run attachment behavior:
- Python `create-request` dry-run attaches a compact batch-plan summary to `request.preflight.batch_plan`.
- Python also attaches the full generated batch plan under `response.plan.batch_plan` when that shape exists.

`validate-gate` behavior:
- CLI accepts `validate-gate` as an operation and rejects `--execute`.
- CLI requires `--quota-gate-record`.
- CLI accepts `--target-operation`, `--quota-gate-ttl-seconds`, and optional create-request binding inputs such as `--request-file`, `--request-schema-file`, media flags, variation limit, small-batch size, and batch size.
- It does not construct `AshrApiClient` and does not require an API key.
- It writes a record with `schema_version=ashr.clone.api_probe_gate_validation.v1`, `function=validate_gate`, `dry_run=true`, `attempts=0`, `request.estimated_calls=0`, and `request.mutates=false`.
- Validation returns `status=ok` with zero issues for a fresh matching gate.
- Validation returns `status=error`, writes the validation record, and exits nonzero for wrong target, stale gate, invalid timestamp, missing timestamp when TTL is enabled, `decision=go` without quota/reset evidence, malformed plan-batch records, and target-binding mismatches.
- TTL default is 86400 seconds; `--quota-gate-ttl-seconds 0` disables age checks.

Mutating execution gate behavior:
- Both Python and TS should validate quota gates before API key lookup or client construction for mutating `--execute`.
- Missing gate blocks unless `--allow-quota-override` is paired with a reason of at least 12 characters.
- A non-plan-batch record blocks.
- A `go` gate without reviewed quota/reset evidence blocks.
- `stop` and `wait` gates block unless an audited override is used.
- Create-request execution requires a target-bound gate matching the current request payload, schema source/fingerprint, media flags, `max_request_variations`, small-batch size, batch size, and modalities.

Open parity decision:
- Python current behavior allows `--allow-quota-override` to return override metadata for any syntactically extractable plan-batch gate after validation has run, even if validation issues such as stale target-bound evidence are present. Current TS allows override for `stop` / `wait` gates but still blocks invalid `go` gates. For strict current-Python parity, TS should mirror Python and persist validation issues under the override. If the desired Round11 policy is stricter, update the Python contract first and record that this is an intentional non-parity fix.

## Required TypeScript Parity Work

1. Add `plan-batch` and `validate-gate` to the TypeScript CLI operation parser and usage text.

2. Add TypeScript CLI options matching Python:
- `--target-operation`
- `--small-batch-size`
- `--batch-size`
- `--quota-record`
- Existing gate options should keep matching Python: `--quota-gate-record`, `--quota-gate-ttl-seconds`, `--allow-quota-override`, and `--quota-override-reason`.

3. Add a TS plan builder equivalent to Python `build_api_probe_batch_plan(...)`.

Required output fields:
- `schema_version`
- `target_operation`
- `created_at`
- `target_binding`
- `output_path`
- `phase_order`
- `small_batch_size`
- `batch_size`
- `operation_mutates`
- `preflight`
- `modality_sequence`
- `quota_stop_go`
- `phases`
- `guardrails`

4. Add TS quota stop/go builder parity.

Required decisions:
- No `--quota-record`: `wait`.
- Quota blocked record: `stop`.
- Retry-after or x-ratelimit reset hint: `wait`.
- Quota/reset header evidence with no block/wait hint: `go`.

Required metadata:
- `source`
- `evidence_present`
- `quota_or_reset_evidence_present`
- `quota`
- `reset`
- `go_conditions`
- `stop_conditions`
- `can_enter_small_batch`
- `can_enter_batch`

5. Add TS target binding builder parity.

For `create-request`, fingerprint the request and optional request schema, record schema source, media flags, variation limit, small-batch size, batch size, and modality order. Do not record raw request payloads in the gate. For non-request targets, emit an operation-scope binding with null request fingerprints.

6. Make TS `create-request` dry-run attach the compact batch-plan summary in `request.preflight.batch_plan` and the full plan in `response.plan.batch_plan` when the record shape supports it.

7. Add a TS `validate-gate` operation that writes the same validation record shape as Python and exits nonzero after writing evidence when invalid.

8. Keep mutating gate validation before API key lookup and before transport construction.

9. Keep schema compatibility with `docs/a1/schemas/api_probe_quota_gate.schema.json`.

10. Ensure all generated evidence remains public-safe:
- No raw request prompts.
- No private ref contents.
- No API key material.
- Only quota/header summaries and redacted metadata.

## Required TypeScript Test Cases

Add or extend `packages/ts/ashr-clone/test/probe.test.mjs` with synthetic temp-file fixtures only.

Plan-batch CLI tests:
- `plan-batch` rejects `--execute`.
- `plan-batch --request-file <fixture> --output <file>` returns code 0, does not call fetch, does not require env keys, writes `function=plan_batch`, `status=blocked`, `response.plan.quota_stop_go.decision=wait`, and inferred `batch_size` from `num_variations`.
- `plan-batch --target-operation create-request` without `--request-file` fails before API key lookup.
- `plan-batch --target-operation create-run` succeeds without `--request-file` and emits operation-scope target binding.
- `plan-batch` with media accepted inputs and media generation sequences `text` before `image` / `audio` / `file` / `video` / `simulation` and does not include raw marker strings from the request payload.
- `plan-batch --small-batch-size 2 --batch-size 5` writes those values into `response.plan`, `target_binding`, and phase requirements.
- `plan-batch --quota-record <synthetic quota block>` writes `decision=stop`.
- `plan-batch --quota-record <synthetic retry-after/reset header record>` writes `decision=wait`.
- `plan-batch --quota-record <synthetic rate-limit evidence without wait/block>` writes `decision=go` and top-level status `planned`.

Create-request dry-run attachment tests:
- Dry-run `create-request` writes `request.preflight.batch_plan.phase_order == ["dry-run", "small-batch", "batch"]`.
- Dry-run `create-request` writes `request.preflight.batch_plan.quota_decision == "wait"` when no quota record is supplied.
- Dry-run `create-request` writes `response.plan.batch_plan.phases[1].phase == "small-batch"` when the client record exposes `response.plan`.

Validate-gate CLI tests:
- `validate-gate --execute` fails before key lookup.
- `validate-gate` without `--quota-gate-record` fails before key lookup.
- Fresh synthetic target-bound gate returns code 0, writes `schema_version=ashr.clone.api_probe_gate_validation.v1`, `function=validate_gate`, `status=ok`, `response.validation.valid=true`, and `issues=[]`.
- Wrong `target_operation` writes `status=error`, exits code 2, and records issue code `target_operation_mismatch`.
- Stale `created_at` with TTL enabled records issue code `stale_gate`.
- Stale `created_at` with `--quota-gate-ttl-seconds 0` does not record `stale_gate`.
- Missing `created_at` with TTL enabled records `missing_created_at`.
- Invalid timestamp records `invalid_created_at`.
- `decision=go` with `source=not-provided` or no quota/reset evidence records `go_without_quota_evidence`.
- Same-operation changed request payload records `target_binding_mismatch`.
- Same-operation changed request schema file records `target_binding_mismatch` or `target_binding_field_mismatch`.
- Same-operation changed media flags, `max_request_variations`, `small_batch_size`, or `batch_size` records a target-binding issue.
- Malformed `phases`, negative `batch_size`, or negative `estimated_real_api_calls` records numeric/shape validation issues.

Mutating execution regression tests:
- `create-request --execute --allow-mutate --max-retries 0` with no gate blocks before API key lookup.
- `create-request --execute` with a TS-generated fresh `plan-batch` gate reaches the missing-key error when no env key is provided, proving the gate itself validated.
- `create-request --execute` with a stale gate blocks before key lookup.
- `create-request --execute` with a target-bound gate generated from a different request blocks before key lookup.
- `create-run --execute` with a fresh operation-scope `plan-batch` gate reaches the missing-key error when no env key is provided.
- Override behavior test should match the Round11 parity decision above, including persisted validation details when an override is allowed.

Schema snapshot tests:
- Assert the TS-generated plan-batch record satisfies the required fields in `docs/a1/schemas/api_probe_quota_gate.schema.json`.
- Assert TS `API_PROBE_BATCH_PLAN_SCHEMA_VERSION`, `API_PROBE_GATE_VALIDATION_SCHEMA_VERSION`, and `API_PROBE_TARGET_BINDING_SCHEMA_VERSION` constants match Python values.

No-network / no-secret tests:
- Patch `globalThis.fetch` to throw in all plan-batch and validate-gate tests and assert it is not called.
- Run plan-batch and validate-gate with empty env and assert errors do not mention `ASHR_API_KEY` / `ASHR_LABS_API_KEY` unless the test intentionally reaches missing-key after successful gate validation.
- Include a raw marker string in a request fixture and assert it does not appear in the generated plan/gate evidence.

## Acceptance Criteria

TS parity is ready when:
- `npm test --prefix packages/ts/ashr-clone` covers plan-batch generation, validate-gate evidence, and mutating gate consumption.
- A TS-generated `plan-batch` gate can be consumed by TS mutating execution guard checks without hash drift.
- TS validation records use the same schema/version/status/issue conventions as Python.
- The checklist tests pass without network, private refs, or real API keys.
