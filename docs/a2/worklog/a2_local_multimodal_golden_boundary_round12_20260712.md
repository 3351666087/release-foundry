# A2 local multimodal golden boundary - Round 12 - 2026-07-12

## Scope and authority

This round changes only A2-owned Provider runtime, release-decision persistence, schemas, fixtures, tests, and this worklog. A1 remains the authenticated evidence producer. A2 remains the sole evaluation and release-decision authority. A3 consumes committed A2 decisions, provenance, review, and reports and never recomputes a grade.

Provider success is not truth. Local or cloud transport completion cannot imply semantic correctness, calibration, or release authority. A2 requires structured validation, golden regression, disagreement analysis, governed trust policy, and human review where required. Every Provider failure remains fail closed.

## Cross-lane synchronization and review

Fetch and review completed during Round 12:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a1-local-sdk-runner = 4a8d0e99cb18676a4ab11205ef7f7ad09d8c9973
origin/agent/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/agent/a3-main-contract-alignment-v2 = ad6113e01f5999f99b378e678d4f0a9602e8fdbc
```

`origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` continues to require provider-neutral A2, fail-closed Provider handling, A2-only decision authority, and read-only A3 consumption. The active A1 branch remains an evidence-production and SDK lane rather than a release-decision authority. The active A3 branches remain compatible with consuming A2 decisions and provenance without recomputation. No cross-lane authority conflict was found.

## Delivered

- Enforced canonical `sha256:<64 lowercase hex>` model digests and content hashes in local smoke evidence.
- Added public-safe duration buckets instead of precise host timing.
- Classified completed, timeout, invalid-response, and unavailable local calls without granting calibration authority.
- Added bounded image size and supported-suffix validation before image bytes are read.
- Preserved bounded generation options and proved caller options cannot replace catalog-controlled endpoint or credential references.
- Added `docs/a2/schemas/local_provider_smoke.schema.json`.
- Added a deterministic reviewed local image Golden case and exact semantic-field evaluation.
- Added a provider-bound HMAC credential-rotation marker that never exposes the credential.
- Added CLI replay coverage for duplicate revocation lists and conflict coverage for changed review age.
- Bound recovery envelopes to the persisted normalized request identity, including trust-policy hash, quality evidence, snapshot, Provider identity, and payload hash.
- Preserved the existing idempotency-conflict contract for changed policies during reconciliation.
- Rejected Ollama responses whose public assistant content is empty, even if a private reasoning channel contains JSON-looking text.

## Prior 20-task disposition

1. **Done:** malformed non-empty model digests are rejected.
2. **Done:** all local smoke content hashes require canonical prefixed SHA-256.
3. **Done:** invalid responses are protocol-reachable and uncalibrated.
4. **Done:** connection/Provider failures are unavailable and uncalibrated.
5. **Done:** duration is emitted only as a coarse public-safe bucket.
6. **Done:** image input has a configurable 1-byte to 50-MiB bound and a 10-MiB default.
7. **Done:** unsupported image suffixes are rejected before file reading.
8. **Done:** `num_predict` 0, 257, and non-integer input fail at the CLI boundary.
9. **Done:** bounded model options reach the Provider adapter.
10. **Done:** caller options cannot override trusted base URL or credential reference.
11. **Done:** duplicate revoked lists normalize to one policy hash and one Provider call on replay.
12. **Done:** changed maximum review age conflicts without a second Provider call.
13. **Done:** reconciliation honors revoked keys and proof hashes supplied through governed policy inputs.
14. **Done:** a canonical-looking but changed stored trust-policy hash fails normalized request binding.
15. **Done:** public local smoke schema added.
16. **Done:** completed, timeout, invalid-response, and unavailable state relationships are schema/test validated.
17. **Done:** deterministic reviewed image Golden fixture added.
18. **Done:** smoke evidence can never mark the Golden result calibrated.
19. **Done:** provider-bound credential-rotation HMAC marker added and tested for stability and rotation.
20. **Externally blocked with executable substitute:** no `POSTGRES_DSN`, `psql`, or Docker is available. The complete SQLite recovery, reconciliation, lease fencing, outbox fencing, atomicity, and idempotency suite passed.

## Real runtime evidence

### Local Ollama/Qwen multimodal

```text
runtime = D:\ReleaseFoundry\ollama\ollama.exe
model = qwen3-vl:4b
model digest = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
image hash = sha256:4f5cf36d805b1017209e9c49a344e3fb68ae79b678f42ef40340b1ba197ee69a
smoke status = completed
capability state = callable
calibration state = uncalibrated
duration bucket = 1_to_5m
repeat response hash = sha256:13808f76408ba29375dd78ea4442e36ede09b752034577ed8904b96a9468cfe6
```

A structured real probe found an important protocol boundary:

```text
Ollama done = true
done reason = stop
public message.content length = 0
private thinking length = 79
formal structured output = missing
Golden regression = blocked
human review required = true
release authority = false
```

The private reasoning text appeared to contain the three expected Golden fields, but it is not governed public model output. A2 deliberately does not parse or promote it. `OllamaAdapter` now rejects empty public content, so this condition becomes `invalid_response` rather than a false successful Judge result.

### DashScope OpenAI-compatible multimodal

```text
DASHSCOPE_API_KEY current process = present
endpoint reached with network permission = true
model attempted = qwen-vl-max
result = HTTP 401 Unauthorized
credential printed or persisted = false
Provider calibration result = unavailable
release PASS possible = false
```

The credential was neither removed nor overwritten. The 401 is recorded as current external evidence and is not represented as a model disagreement or calibration observation.

### PostgreSQL discovery

```text
POSTGRES_DSN process = missing
psql = missing
docker = missing
```

SQLite is the executable parity substitute for this round, not evidence that PostgreSQL itself passed.

## Microscopic simulations

### Micro 1 - private reasoning cannot become Judge output

A real local image request returned no public assistant content but placed JSON-looking text in a private reasoning field. A2 rejected the response rather than copying private reasoning into `output_text`. The Golden gate received no structured output, returned `uncalibrated`, required human review, and retained `release_authority=false`.

### Micro 2 - normalized policy recovery tamper

A Provider-completed recovery envelope was created with a duplicate-list policy whose normalized hash was persisted in the operation request identity. The envelope policy hash was replaced with another canonical SHA-256 value and the envelope's own hash was recomputed. Loading still failed because A2 reconstructed the normalized request identity and compared it to the immutable operation request hash. No decision or outbox row was committed.

## A1/A2/A3 macroscopic simulations

### Macro 1 - valid A1 evidence with invalid Provider content

A1 supplies a complete, authenticated, five-field-scoped evidence bundle. A2 verifies the bundle, freezes its evidence snapshot, authorizes a Provider call, and receives transport completion with empty governed content. A2 classifies the Provider response as invalid, cannot validate structured Judge output, and produces no false PASS. A3 may display the blocked/incomplete state and provenance but cannot reinterpret private reasoning or recompute a grade.

### Macro 2 - policy changes during uncertain remote completion

A1 evidence and the original quality proof reserve one idempotent A2 operation. The Provider call enters an uncertain window and is later reconciled as remotely completed. Before commit, the trust policy changes by revoking a key or proof hash. The reconstructed input no longer matches the reserved request identity, so A2 raises an idempotency conflict and commits neither a decision nor an A3 outbox event. A3 therefore has no release-ready artifact to consume.

## Validation

```text
Focused multimodal/provider tests = 31 passed, 12 subtests passed
Release/recovery/fencing suite = 56 passed, 19 subtests passed
Full A2 suite in sandbox = 355 passed, 1099 subtests passed, 1 filesystem-permission failure
Filesystem-dependent installer checksum test with approved D:\ReleaseFoundry access = 1 passed
Effective full A2 result = 356 passed, 1099 subtests passed
Generated fixtures = 56/56 matched
Changed Python files parsed with AST = 11/11 passed
git diff --check = passed
```

The ordinary `compileall` command could not write existing protected `__pycache__` directories. This was a filesystem limitation rather than a syntax failure; read-only AST parsing of every changed Python file passed. Only known `jsonschema.RefResolver` deprecation warnings and Git line-ending notices remained.

## Growth auditor

The growth auditor confirms before commit:

- only A2-owned paths are changed;
- main, A1, A3, and strategy refs were reviewed;
- all prior 20 tasks are completed or carry exact external-blocker evidence plus an executable offline substitute;
- two microscopic and two A1/A2/A3 macroscopic simulations are documented;
- local callability and private reasoning are not mislabeled as calibration;
- HTTP 401 is not fabricated into cloud-model evidence;
- Provider, policy, recovery, reconciliation, and A3 handoff remain fail closed;
- no raw credential, token, `ReleaseFoundry_key.txt`, or `docs/evidence/private_refs/` content is included;
- commit, push, and remote SHA equality remain mandatory after this worklog is staged.

## Exactly 20 narrow tasks for Round 13

1. Add an explicit normalized Provider result field distinguishing empty public content from malformed JSON.
2. Add an Ollama fixture where public content is empty and private thinking contains malicious PASS text.
3. Add an Ollama fixture where both public content and private thinking exist and only public content is validated.
4. Add a schema for local multimodal Golden results.
5. Validate passed, missing-field, mismatched-field, and smoke-authority-blocked Golden results against the schema.
6. Bind Golden cases to model digest, prompt hash, generation options hash, and artifact hash.
7. Reject Golden evaluation when the runtime model digest differs from the governed case binding.
8. Add a deterministic disagreement receipt for local missing output versus a synthetic governed cloud output.
9. Add a disagreement receipt state for cloud authentication failure without claiming semantic disagreement.
10. Add a minimum multi-case Golden suite aggregator with explicit pass-rate and abstention-rate thresholds.
11. Require every Golden suite result to retain individual case hashes rather than only an aggregate score.
12. Add human-review routing for a model that passes some Golden fields but fails a safety field.
13. Add credential-marker metadata to secret-safe real-probe evidence without persisting the credential.
14. Add a test proving credential-marker changes cannot alter an already committed decision.
15. Add a governed model-options allowlist per Provider protocol.
16. Reject unsupported Ollama options rather than forwarding arbitrary keys.
17. Add an OpenAI-compatible multimodal adapter test with data-URL image content and strict JSON response validation.
18. Add HTTP 401/403 classification tests that remain unavailable and never retry as transient failures.
19. Recheck PostgreSQL availability and run parity if a real DSN/service appears; otherwise repeat exact blocker discovery and SQLite fencing tests.
20. Run a real local Golden suite after resolving the Qwen thinking/public-content mode and compare it with the existing fail-closed baseline.
