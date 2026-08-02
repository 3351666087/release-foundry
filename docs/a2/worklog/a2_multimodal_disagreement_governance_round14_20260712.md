# A2 multimodal disagreement governance and fallback - Round 14 - 2026-07-12

## Scope and authority

This round changes only A2-owned Provider Gateway, Provider runtime, local multimodal calibration, schemas, tests, and this worklog. A1 remains the authenticated evidence producer. A2 remains the sole release-decision authority. A3 consumes committed A2 decisions and provenance without recomputing scores, policy, or release state.

Provider and model output is never treated as truth. A transport-successful or parseable response is only an observation. Structured validation, immutable model/runtime binding, Golden regression, disagreement analysis, policy, and human review remain required. Provider failure, missing public content, missing calibration, and failed safety-critical cases remain fail closed.

## Cross-lane synchronization and review

Two initial fetch attempts failed with:

```text
Failed to connect to github.com:443
```

The final retry succeeded on 2026-07-12. Freshly reviewed refs:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = f9562494d427c430c043c4316d91eb2510df62a1
origin/agent/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a3-main-contract-alignment-v2 = c8420813ed6cb94535bd108b30bd97663b906bdb
origin/main strategy blob = 575b31b80981542fc96f9a9310e66a9318974abb
```

`origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` still requires Provider-neutral A2, fail-closed evaluation, A2-only release authority, and A3 consumption without recomputation.

A1's active branch retains restart-safe Provider dispatch journal work and adds Python CLI fixture compatibility. A2's immutable input and model bindings remain compatible with restart-safe delivery. A3's active alignment branch now executes its Golden agent tool chain in addition to sealing candidate evidence. That does not transfer evaluation authority: A3 may exercise or present a committed A2 contract, but it may not derive a replacement release decision.

## Delivered

- Added a JSON schema for governed local multimodal Golden-suite results.
- Added a JSON schema for all governed multimodal disagreement-receipt states.
- Rejected empty case IDs, duplicate case IDs, and duplicate case-result hashes.
- Added explicit safety-critical case IDs and a non-bypassable `safety_critical_case_failed` gate.
- Preserved numeric pass/abstention thresholds without allowing aggregate weighting to conceal a failed safety case.
- Bound disagreement receipts to exact local and cloud provider/model/version records.
- Classified absent or malformed runtime binding as `not_comparable` without semantic comparison.
- Added deterministic, public-safe human-review packets for true semantic disagreements.
- Added governed Provider fallback evaluation: calibrated fallback can be available for review, but cannot create release authority or manufacture PASS.
- Added value/range validation for governed Ollama and OpenAI-compatible model options.
- Proved model-option dictionary order does not change logical-call identity.
- Added a public-safe credential-generation marker to Provider request identity and audit metadata.
- Proved a credential generation change cannot replay the prior generation's cached authentication result.
- Added OpenAI-compatible missing choices, missing message content, and empty public-content parity with Ollama.
- Ran a fresh real Qwen text-only structured probe.
- Installed and ran a second real local vision model, `llava:7b`.

## Prior 20-task disposition

1. **Done:** Golden-suite and disagreement-receipt JSON schemas added.
2. **Done:** all five disagreement states validate against the receipt schema.
3. **Done:** passed and blocked Golden suites validate against the suite schema.
4. **Done:** duplicate case IDs are rejected.
5. **Done:** duplicate case-result hashes are rejected.
6. **Done:** empty governed case IDs are rejected.
7. **Done:** safety-critical cases have an explicit gate that aggregate thresholds cannot hide.
8. **Done:** deterministic semantic-disagreement review packet added.
9. **Done:** receipts bind exact local/cloud provider, model, and version.
10. **Done:** absent or invalid binding becomes non-comparable.
11. **Done:** OpenAI-compatible empty public content has Ollama-equivalent governed rejection.
12. **Done:** missing choices, message, and content response shapes are tested.
13. **Done:** option values and ranges are validated before network invocation.
14. **Done:** option-order normalization preserves logical-call identity.
15. **Done:** credential-generation marker is included in public-safe audit metadata.
16. **Done:** rotated credential generations cannot share cached authentication results.
17. **Done:** fallback cannot upgrade failed primary execution into PASS; calibration only makes it review-available.
18. **Done and fail-closed:** a real local text-only Qwen probe again emitted no governed public output.
19. **Externally blocked with executable substitute:** no `POSTGRES_DSN`, `psql`, or Docker is available; SQLite persistence/fencing coverage ran in the A2 suite.
20. **Done and fail-closed:** `llava:7b` produced parseable public JSON but omitted a required field, so it is not Golden-compatible yet.

## Real runtime evidence

### Qwen text-only isolation probe

```text
runtime = D:\ReleaseFoundry\ollama\ollama.exe
model = qwen3-vl:4b
model digest = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
request mode = text only, format=json, temperature=0, num_predict=256, /no_think
done = true
done_reason = length
public content length = 0
private thinking length = 1171
prompt_eval_count = 54
eval_count = 256
wall duration = 56.1 seconds
```

The empty public output is therefore not isolated to image templating. Private thinking remains ineligible as Judge output. The governed result is invalid/blocked, never PASS.

### LLaVA second-model multimodal probe

```text
runtime = D:\ReleaseFoundry\ollama\ollama.exe
model = llava:7b
model digest = sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081
installed size = 4,733,363,377 bytes
artifact = D:\ReleaseFoundry\a2-local-smoke.png
artifact size = 1,934 bytes
request mode = image, format=json, temperature=0, seed=7, num_predict=128
done = true
done_reason = stop
prompt_eval_count = 645
eval_count = 16
wall duration = 50.946 seconds
```

Public output:

```json
{"contains_text": true, "primary_color": "gray"}
```

The response is public and JSON-parseable, unlike the Qwen observations, but it omits the required `safety_risk` field. It therefore fails the requested structured-output contract and cannot enter the Golden suite as a passing observation. The color observation also cannot be treated as truth without a version-bound expected case and calibration. LLaVA is a viable protocol/model candidate for further constrained decoding work, not a release Judge.

## PostgreSQL discovery

```text
POSTGRES_DSN = absent
psql = absent
docker = absent
```

Real PostgreSQL parity remains externally blocked. SQLite remains the executable substitute for deterministic persistence, recovery, idempotency, atomicity, and fencing behavior. SQLite evidence is not represented as PostgreSQL parity.

## Microscopic simulations

### Micro 1 - aggregate threshold passes while a safety-critical case fails

A suite has nine ordinary passing cases and one failed safety-critical case. The numeric pass rate can meet a permissive threshold, but aggregation records the exact failed safety case and adds `safety_critical_case_failed`. The suite is blocked, human review is required, and `release_authority=false`. Numeric weighting cannot erase the safety failure.

### Micro 2 - credential generation rotates after cached authentication failure

Generation A receives a terminal authentication failure and its logical call is cached. Generation B uses the same provider, model, payload, and idempotency key, but supplies a different public-safe credential-generation HMAC marker. The marker participates in request identity, so B cannot replay A's failure. Neither marker exposes credential material, and a successful B observation still requires calibration and policy before any release decision.

## A1/A2/A3 macroscopic simulations

### Macro 1 - restart-safe A1 evidence, failed primary, and uncalibrated fallback

A1 resumes its journal and delivers exactly one complete, authenticated, correctly scoped evidence bundle. A2 freezes and verifies the bundle. The primary Provider fails. A fallback returns structured output but has no matching Golden calibration for its exact model/version/options binding. A2 records both attempts and blocks fallback promotion with `fallback_not_calibrated`; no PASS is produced. A3 can display the committed blocked/incomplete state but cannot reinterpret fallback availability as release readiness.

### Macro 2 - semantic disagreement review and sealed A3 consumption

A1 supplies immutable version-bound evidence. A2 receives calibrated local and cloud outputs with exact provider/model/version bindings. Their governed output hashes differ, so A2 creates a deterministic `semantic_disagreement` receipt and review packet, requires human review, and retains sole release authority. After review and policy, A2 commits the unique decision. A3 consumes and seals that decision and provenance. Any A3-side score recomputation or substituted decision hash is outside the contract.

## Validation

```text
Focused multimodal/Gateway/runtime tests = 44 passed
Full A2 suite in sandbox = 373 passed, 1 filesystem-permission error
Filesystem-dependent checksum test with approved D:\ReleaseFoundry access = 1 passed
Effective full A2 result = 374 passed
Generated fixtures = 56/56 matched
git diff --check = passed
```

Only known `jsonschema.RefResolver` deprecation warnings and a Git line-ending notice remained.

## Growth auditor

Before commit, the growth auditor confirms:

- all changes are A2-owned;
- fresh main, A1, A3, and strategy refs were fetched and reviewed after two recorded network failures;
- all prior 20 tasks are completed or have exact external blocker evidence plus an executable offline substitute;
- two microscopic and two A1/A2/A3 macroscopic simulations are documented;
- model output remains an observation, never truth or release authority;
- Qwen private thinking is not promoted to public output;
- LLaVA's parseable but incomplete JSON is rejected rather than repaired into a passing observation;
- safety-critical failure cannot be averaged away;
- fallback availability cannot manufacture PASS;
- credential rotation changes cache identity without exposing credentials;
- no raw secret, token, `ReleaseFoundry_key.txt`, or `docs/evidence/private_refs/` content is included;
- explicit A2-only staging, commit, push, and remote-SHA equality are required.

## Exactly 20 narrow tasks for Round 15

1. Add a JSON schema for semantic-disagreement review packets.
2. Validate deterministic review packets against that schema.
3. Add a JSON schema for Provider fallback evaluations.
4. Validate blocked and review-available fallback outputs against that schema.
5. Bind fallback evaluations to exact primary and fallback provider/model/version records.
6. Reject fallback review availability when either runtime binding is missing.
7. Bind fallback calibration to prompt, options, and artifact hashes.
8. Reject fallback calibration reuse across a changed generation-options hash.
9. Add a governed structured-output repair state that can never silently modify an observation.
10. Store original and repaired-output hashes when deterministic repair is explicitly allowed.
11. Prove missing required fields remain blocked when no repair policy is configured.
12. Add per-field safety severity so a missing safety field is always review-required.
13. Add LLaVA exact-model Golden candidate fixtures without marking them calibrated.
14. Run a second LLaVA probe with schema stated in both prompt and deterministic local validator.
15. Run a repeat LLaVA probe and compare deterministic output hashes and latency.
16. Add local-model resource observations for installed bytes, wall time, and token counts.
17. Add a maximum local-Judge latency policy that yields INCOMPLETE rather than PASS.
18. Recheck PostgreSQL availability and run parity if available; otherwise rerun discovery and SQLite fencing.
19. Simulate A1 replay of the same evidence against rotated Provider credentials and prove one A2 decision identity.
20. Simulate A3 consumption of a reviewed disagreement decision and reject any recomputed release state.
