# Round11 TS Probe Reviewer Test Matrix

Scope: review `packages/ts/releasefoundry/test/probe.test.mjs` for the planned TypeScript probe standalone `plan-batch` and `validate-gate` CLI parity. This matrix is reviewer guidance only. It does not require reading private refs, secrets, or calling the ReleaseFoundry API.

## Current Coverage Snapshot

Post-integration note: the Round11 implementation added direct standalone `plan-batch` and `validate-gate` tests, including local-only key isolation, media target binding, quota-header `go`, matching validation, and stale/wrong-target/wrong-request failures. The matrix below remains the reviewer backlog for broader negative coverage and CI hardening.

- Existing tests cover regular dry-run probe commands, mutating execute guard ordering, invalid quota gate records, stale TTL, wrong target operation, same-operation wrong request binding, override metadata, and media preflight blocking.
- Existing tests do not directly exercise `plan-batch` or `validate-gate` as standalone local CLI operations.
- The local operation surface in `src/probe.ts` includes `plan-batch`, `validate-gate`, `--quota-record`, `--target-operation`, `--small-batch-size`, `--batch-size`, target binding generation, validation records, and validation stderr behavior.

## High-Risk Failure Paths

1. Local commands accidentally construct `ReleaseFoundryApiClient`, inspect API-key env vars, or call `fetch`.
2. `plan-batch --execute` or `validate-gate --execute` slips through as a real/API path.
3. Missing `--request-file` for `plan-batch --target-operation create-request` is not blocked before client/key lookup.
4. `plan-batch` records raw request payloads, raw quota payloads, secret-like values, or exact private quota details.
5. `plan-batch` emits `go` without reviewed quota/reset evidence.
6. `validate-gate` returns exit 0 for invalid gates or fails to persist a public-safe validation record.
7. TTL handling allows stale gates, missing timestamps, invalid timestamps, or negative TTL values.
8. Target binding misses request hash, schema hash, guardrail flags, modality order, batch size, or max-variation drift.
9. A gate generated for one create-request payload validates against another payload under the same operation.
10. Validation behavior diverges between stdout/stderr, output-file mode, and `--output -`.

## Test Matrix

| ID | Area | Scenario | Inputs | Expected Result | Risk Covered |
| --- | --- | --- | --- | --- | --- |
| R11-01 | Local isolation | `plan-batch` runs without API env or network | Monkeypatch `globalThis.fetch`; pass empty env; `--output - --print-record` | Exit 0, no fetch, no API-key hint, `function=plan_batch`, `dry_run=true` | Prevents paid/API side effects |
| R11-02 | Local isolation | `validate-gate` runs without API env or network | Fresh valid synthetic gate; empty env; fetch monkeypatch | Exit 0, no fetch, no API-key hint, `function=validate_gate` | Confirms validator is local-only |
| R11-03 | Execute guard | Local ops reject `--execute` | `plan-batch --execute`; `validate-gate --execute` | Exit 2, error says planning/read-only, no key hint | Blocks accidental real calls |
| R11-04 | Required request | `plan-batch create-request` requires request file | `plan-batch --target-operation create-request` without `--request-file` | Exit 2 before key/client lookup | Avoids incomplete gate records |
| R11-05 | Non-request target | `plan-batch create-run` does not require request file | `plan-batch --target-operation create-run --output - --print-record` | Exit 0, target binding scope is operation, no raw request fields | Confirms non-request parity |
| R11-06 | No quota evidence | Planner blocks by default | `plan-batch` with request file but no `--quota-record` | Record status `blocked`, `quota_stop_go.decision=wait`, no client lookup | Prevents false go gates |
| R11-07 | Quota stop | Planner preserves public-safe stop | Synthetic quota error record with secret-like field | `decision=stop`, output redacts secret, no exact private quota counters in public-safe fields | Secret and quota safety |
| R11-08 | Reset wait | Planner respects retry/reset headers | Synthetic `retry-after` or reset header record | `decision=wait`, reset metadata present, no mutation allowed | Avoids reset-window spend |
| R11-09 | Quota go | Planner allows go only with evidence | Synthetic nonblocked quota/header evidence | `decision=go`, `can_enter_small_batch=true`, evidence markers present | Positive path |
| R11-10 | Request binding | Planner emits target binding | Create-request file plus default schema | `target_binding.schema_version`, request fingerprint, schema source, modality list, batch sizes, `raw_request_not_recorded=true` | Binds gate to payload |
| R11-11 | Schema binding | Explicit request schema affects binding | Same request with `--request-schema-file` | Schema fingerprint/source differ from default-source plan | Blocks schema drift |
| R11-12 | Guardrail binding | Media flags affect binding | Same request with and without `--allow-media-generation` / `--allow-non-text-inputs` | Different binding fingerprint and fields | Blocks unsafe flag reuse |
| R11-13 | Batch binding | Batch-size inputs affect binding | Same request with changed `--small-batch-size` or `--batch-size` | Different binding fingerprint and validation mismatch | Blocks scale-up reuse |
| R11-14 | Valid gate | `validate-gate` accepts matching fresh gate | Gate from matching `plan-batch`; same request/flags | Exit 0, `status=ok`, `issues=[]` | End-to-end local parity |
| R11-15 | Wrong operation | Validator rejects target mismatch | `create-run` validation against create-request gate | Exit 2, `target_operation_mismatch`, no key hint | Operation binding |
| R11-16 | Wrong payload | Validator rejects same-operation request drift | Gate from request A, validate with request B | Exit 2, `target_binding_mismatch` or field mismatch | Payload binding |
| R11-17 | Missing binding | Validator rejects create-request gate lacking binding when request supplied | Old-style gate with `target_operation=create-request`, no `target_binding`, plus `--request-file` | Exit 2, `missing_target_binding` | Backward unsafe gate block |
| R11-18 | TTL stale | Validator rejects stale gate | Old `created_at`; default TTL | Exit 2, `stale_gate`, no key hint | Freshness |
| R11-19 | TTL disabled | Validator allows stale timestamp only when explicit | Same stale gate with `--quota-gate-ttl-seconds 0` | No stale issue; subsequent result depends on other validation fields | Auditable override of freshness only |
| R11-20 | Timestamp shape | Validator rejects malformed/missing timestamp | Invalid `created_at`; missing `created_at` with TTL > 0 | Exit 2, `invalid_created_at` or `missing_created_at` | Freshness integrity |
| R11-21 | Numeric shape | Validator rejects invalid plan numerics | Gate with negative/non-integer `batch_size`, `small_batch_size`, phase estimates | Exit 2, `invalid_numeric_binding` | Schema sanity |
| R11-22 | Phase shape | Validator rejects malformed phases | `phases` not array or entries not objects | Exit 2, `invalid_phases` or `invalid_phase` | Planner contract sanity |
| R11-23 | Output mode | Validation failure writes safe record | Invalid gate with explicit output path | Exit 2, output JSON `function=validate_gate`, `status=error`, issues listed, no raw request | Audit evidence completeness |
| R11-24 | Stdout mode | `--output -` does not create a file | `plan-batch --output - --print-record`; `validate-gate --output - --print-record` | JSON printed, no filesystem output, stderr only on invalid validation | CLI ergonomics and safety |
| R11-25 | Default output | Local-op defaults stay under private refs | Invoke local ops without `--output` in temp cwd or inspect computed summary | Output path uses `docs/evidence/private_refs` convention | Owned private-evidence boundary |

## Reviewer Acceptance Bar

- Add at least one direct standalone `plan-batch` success test and one direct standalone `validate-gate` success test.
- Add negative local-op tests proving invalid gates fail before key/client/fetch resolution.
- Add target-binding drift tests for request payload, explicit schema, media flags, and batch sizing.
- Assert all local-op outputs are public-safe summaries: no raw request body, no API key/env value, no bearer token, and no raw private quota payload.
- Keep all test fixtures synthetic and under temp directories; do not read ignored private evidence or call the ReleaseFoundry API.
