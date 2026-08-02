# A2 multimodal governed output and calibration replay - Round 13 - 2026-07-12

## Scope and authority

This round changes only A2-owned Provider Gateway, Provider runtime, multimodal calibration, schemas, fixtures, tests, and this worklog. A1 remains the authenticated evidence producer. A2 remains the sole release-decision authority. A3 consumes committed A2 decisions and provenance without recomputing them.

Provider/model output is not truth. Transport success, private reasoning, model confidence, and smoke callability cannot imply semantic correctness or PASS. Structured validation, immutable runtime binding, Golden regression, disagreement classification, policy, and human review remain mandatory. Every Provider failure remains fail closed.

## Cross-lane synchronization and review

Reviewed refs:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = f9562494d427c430c043c4316d91eb2510df62a1
origin/agent/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a3-main-contract-alignment-v2 = 46e9a85aa2cc8b1ce3e32951f8801cf6112ef13b
origin/main strategy blob = 575b31b80981542fc96f9a9310e66a9318974abb
```

`origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` continues to require Provider-neutral A2, fail-closed evaluation, A2-only decision authority, and A3 read-only consumption. A1's active branch adds restart-safe Provider dispatch journal/stream-integrity work. A3's active work adds sealed candidate delivery evidence. A2's immutable input binding, recovery, reconciliation, and provenance contracts remain aligned with both.

## Delivered

- Added a schema for governed local multimodal Golden results.
- Bound Golden cases to model digest, prompt hash, generation-options hash, and artifact hash.
- Rejected missing or mismatched runtime bindings.
- Added Golden-suite pass-rate and abstention-rate gates while retaining every case-result hash.
- Added deterministic disagreement receipts separating missing local output, unavailable cloud output, non-comparability, agreement, and semantic disagreement.
- Classified HTTP 401/403 as terminal `authentication_failed`, with no transient retry.
- Distinguished empty governed public content from other malformed/invalid output.
- Proved private Ollama thinking is never promoted into public Judge output.
- Added per-protocol governed model-option allowlists for Ollama and OpenAI-compatible calls.
- Added OpenAI-compatible data-URL image and strict structured-output coverage.
- Added a public-safe credential-rotation marker to smoke evidence; marker changes do not alter Golden decision identity.
- Added explicit human-review coverage for a safety-field regression.

## Prior 20-task disposition

1. **Done:** `failure_detail` distinguishes empty public content from other invalid output.
2. **Done:** malicious PASS-like private thinking with empty public content is rejected in the adapter contract test.
3. **Done:** when public content and private thinking coexist, only public content is returned.
4. **Done:** local multimodal Golden-result schema added.
5. **Done:** pass, missing output, mismatch, and smoke-authority-blocked results are schema validated.
6. **Done:** model, prompt, generation options, and artifact bindings added.
7. **Done:** runtime model-digest mismatch fails closed.
8. **Done:** local-missing versus governed-cloud output has a deterministic receipt.
9. **Done:** cloud authentication failure is unavailable, not semantic disagreement.
10. **Done:** multi-case suite aggregation enforces pass and abstention rates.
11. **Done:** suite provenance retains individual case-result hashes.
12. **Done:** safety-field mismatch explicitly requires human review.
13. **Done:** credential marker is emitted in secret-safe smoke evidence.
14. **Done:** rotation-marker changes cannot change Golden decision identity.
15. **Done:** Ollama and OpenAI-compatible protocols enforce option allowlists.
16. **Done:** unsupported Ollama options are rejected before network access.
17. **Done:** OpenAI-compatible data-URL image and strict JSON validation are tested.
18. **Done:** HTTP 401/403 are terminal and a three-attempt policy still makes one call.
19. **Externally blocked with executable substitute:** `POSTGRES_DSN`, `psql`, and Docker remain unavailable; the SQLite persistence/recovery/fencing suite ran in the full A2 suite.
20. **Attempted and fail-closed:** two real Qwen probes still produced no governed public content. Golden calibration remains blocked rather than consuming private thinking.

## Real runtime evidence

### Local Ollama/Qwen multimodal

```text
runtime = D:\ReleaseFoundry\ollama\ollama.exe
model = qwen3-vl:4b
model digest = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
artifact hash = sha256:4f5cf36d805b1017209e9c49a344e3fb68ae79b678f42ef40340b1ba197ee69a
```

Fresh governed-output probes:

```text
probe 1 option = think=false
done = true
done_reason = stop
public content = empty
private thinking length = 66
duration = 97.05 seconds
prompt_eval_count = 1103
eval_count = 19

probe 2 prompt control = /no_think
done = true
done_reason = length
public content = empty
private thinking length = 258
duration = 15.44 seconds
prompt_eval_count = 1100
eval_count = 64
```

Both probes are `invalid_response` with `failure_detail=empty_public_content`. Neither is a Golden observation, calibration pass, semantic disagreement, or release PASS.

### DashScope OpenAI-compatible multimodal

The previously verified real `qwen-vl-max` request reached the endpoint but returned HTTP 401 Unauthorized. The credential was not printed, persisted, removed, or overwritten. The governed classification is `authentication_failed`, terminal/non-retryable, cloud unavailable, and never PASS.

### PostgreSQL discovery

```text
POSTGRES_DSN = false
psql = false
docker = false
```

SQLite is an executable substitute for persistence, recovery, idempotency, atomicity, and fencing checks. It is not PostgreSQL parity evidence.

## Microscopic simulations

### Micro 1 - malicious private PASS with empty public output

The Provider response places PASS-looking JSON in private thinking and leaves public assistant content empty. The Ollama adapter rejects it before semantic validation. The Gateway records `invalid_response/empty_public_content`; Golden evaluation receives no governed structured output, requires human review, and retains `release_authority=false`.

### Micro 2 - credential rotates after a decision observation

Two secret-safe smoke records differ only in their HMAC credential-rotation marker. Golden evaluation deliberately excludes smoke metadata from semantic decision identity, so both produce the same blocked result. Rotation remains operational provenance and cannot mutate or replay-rewrite an already governed decision.

## A1/A2/A3 macroscopic simulations

### Macro 1 - restart-safe A1 delivery plus Provider authentication failure

A1's restart-safe journal delivers one complete, authenticated, correctly scoped evidence bundle. A2 freezes and validates it, then the cloud adapter receives HTTP 401. A2 performs one attempt, commits no false model observation, classifies cloud output unavailable, and produces a fail-closed decision. A3 may display the committed status/provenance but cannot reinterpret the failure as PASS.

### Macro 2 - A2 committed decision consumed by sealed A3 delivery

A1 supplies version-bound evidence; A2 validates it, runs governed evaluation, persists the unique decision and outbox provenance, and exposes only the committed A3 consumption contract. A3 seals and delivers that exact candidate packet. Any A3-side recomputation or changed decision identity is outside the contract and cannot replace the A2 decision.

## Validation

```text
Focused Round 13 tests = 38 passed
Full A2 suite in sandbox = 367 passed, 1 expected filesystem-permission error
Filesystem-dependent checksum test with approved D:\ReleaseFoundry access = 1 passed
Effective full A2 result = 368 passed
Generated fixtures = 56/56 matched
git diff --check = passed
```

Only known `jsonschema.RefResolver` deprecation warnings and a Git line-ending notice remained.

## Growth auditor

Before commit, the growth auditor confirms:

- only A2-owned files are in this round;
- main, A1, A3, and strategy refs were reviewed;
- all prior 20 tasks are completed or carry exact blocker evidence plus an executable offline substitute;
- two microscopic and two A1/A2/A3 macroscopic simulations are documented;
- public content, not private reasoning, is the only eligible Judge output;
- local/cloud Provider success remains non-authoritative;
- authentication and malformed-output failures cannot retry into or imply PASS;
- Golden cases and suites retain immutable provenance and no release authority;
- no raw secret, token, `ReleaseFoundry_key.txt`, or `docs/evidence/private_refs/` content is included;
- explicit A2-only staging, commit, push, and remote-SHA equality are still required.

## Exactly 20 narrow tasks for Round 14

1. Add JSON schemas for Golden-suite and disagreement-receipt outputs.
2. Validate every disagreement state against its schema.
3. Validate passed and blocked Golden-suite outputs against their schema.
4. Add duplicate case-ID rejection in Golden-suite aggregation.
5. Add duplicate case-result-hash rejection in Golden-suite aggregation.
6. Require every suite case to expose a non-empty governed case ID.
7. Add explicit safety-critical case weighting without allowing weighted PASS to hide a failed safety case.
8. Add a deterministic review packet for semantic disagreement.
9. Bind disagreement receipts to local/cloud model records and versions.
10. Reject disagreement comparison when either runtime binding is absent.
11. Add OpenAI-compatible empty-public-content classification parity with Ollama.
12. Add OpenAI-compatible response-shape tests for missing choices and missing message content.
13. Add option value/range validation, not only option-name allowlisting.
14. Prove option-order normalization produces the same Provider logical-call identity.
15. Add a credential-generation marker to Provider audit metadata without exposing credential material.
16. Prove credential rotation cannot reuse an unsafe cached authentication-failure result across generations.
17. Add deterministic provider fallback policy tests where fallback cannot upgrade a failed primary into PASS without calibration.
18. Run a real local text-only structured Qwen probe to isolate multimodal template behavior from general JSON behavior.
19. Recheck PostgreSQL availability and run real parity if available; otherwise rerun exact discovery and SQLite fencing evidence.
20. Evaluate a second local vision model/protocol candidate and record governed public-output, resource, and Golden compatibility evidence.
