# A2 provider capability calibration - Round 11 - 2026-07-12

## Scope and authority

This round changes only A2-owned runtime, installer, tests, and worklog files. A1 remains the authenticated evidence producer. A2 remains the sole evaluation and release-decision authority. A3 consumes A2 decision, provenance, review, and report output and does not recompute a grade.

Provider output is not truth. This round deliberately labels a successful local smoke as callable but uncalibrated; release eligibility still requires structured validation, calibration, golden regression, disagreement analysis, and human review where policy requires it.

## Cross-lane synchronization and review

Fetch completed successfully on 2026-07-12:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 4a8d0e99cb18676a4ab11205ef7f7ad09d8c9973
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = 45bec48e65f3ae11f0252174990365eb20e46ef6
fetch exit = 0
```

`origin/main:docs/strategy` still establishes provider-neutral A2, fail-closed Provider failure, A2-only release authority, and A3 consumption without recomputation. A1's active branch adds provider-neutral Python/TypeScript model adapters and hosted-secret response validation but explicitly does not replace A2 Judge semantics. A3's active contract branch strengthens trusted request boundaries and remains compatible with consumption of A2 provenance. No authority conflict was found.

## Delivered

- Added finite, strictly-positive timeout validation and bounded `num_predict` validation to the Ollama smoke CLI.
- Added bounded Ollama generation options (`num_predict`, zero temperature) through the unified Provider Gateway.
- Added model digest to public-safe local smoke evidence.
- Added explicit capability states: `callable`, `protocol_reachable`, and `unavailable`.
- Added explicit `calibration_state=uncalibrated`, preventing a successful smoke from being represented as calibrated Judge truth.
- Added subprocess coverage for completed and timed-out Ollama calls, exit codes, public-safe output, timeout boundaries, and absence of prompt/raw Provider output.
- Added normalized trust-policy replay tests for reordered lists and changed revocation sets.
- Added reconciliation coverage for proof revocation supplied through a complete policy object.
- Added provider-completed recovery coverage for duplicate revoked-key and revoked-proof lists.
- Added malformed bundle and quality-proof sanitization plus missing-proof fail-before-Provider coverage.
- Added D-only download-path enforcement and preservation of a caller-owned archive source on checksum failure.
- Moved the installer's 20 GiB capacity check after dry-run/path validation so dry run remains side-effect-free and path violations remain deterministically testable.
- Isolated subprocess tests from a real inherited `DASHSCOPE_API_KEY`, preventing host credentials from changing deterministic negative-test behavior.

## Prior 20-task disposition

1. **Done:** timeout is finite and strictly positive.
2. **Done:** timeout subprocess returns exit 2 and public-safe JSON.
3. **Done:** completion subprocess returns exit 0 without raw output.
4. **Done:** model digest is recorded.
5. **Done:** protocol reachability and callability are distinct; calibration is separately uncalibrated.
6. **Done:** timeout can never become callable.
7. **Done:** generation is bounded by `num_predict` and zero temperature.
8. **Done:** real bounded local image smoke completed; exact evidence is below.
9. **Done:** reordered equivalent policy replays without a second Provider call.
10. **Done:** changed revocation policy fails closed without a second Provider call.
11. **Done:** reconciliation honors proof revocation from a supplied policy object.
12. **Done:** duplicate revoked-key/proof lists normalize deterministically through recovery.
13. **Done:** malformed quality-proof JSON is sanitized.
14. **Done:** malformed bundle JSON is sanitized.
15. **Done:** missing quality-proof file fails before Provider invocation.
16. **Done:** explicit non-D download path is rejected.
17. **Done:** checksum cleanup preserves the caller-owned local source archive.
18. **Done:** after the credential changed, a secret-safe direct probe returned HTTP 200 and the same credential completed a structured call through A2's unified Provider Gateway.
19. **Partially done with truthful boundary:** real local and Qwen calls now both exist, but the local smoke did not retain a governed semantic output suitable for a signed disagreement receipt. No artificial disagreement artifact is fabricated; existing signed disagreement and human-review gates remain the offline substitute.
20. **Blocked externally:** `POSTGRES_DSN` is absent and neither `psql` nor Docker is available. SQLite recovery, fencing, idempotency, and atomic outbox tests remain the executable substitute.

## Real runtime evidence

Local runtime:

```text
runtime = D:\Ashr\ollama\ollama.exe
runtime version = 0.31.2
model = qwen3-vl:4b
model digest = sha256:1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683
image sha256 = 4f5cf36d805b1017209e9c49a344e3fb68ae79b678f42ef40340b1ba197ee69a
timeout = 420 seconds
num_predict = 8
status = completed
capability_state = callable
calibration_state = uncalibrated
response_hash = sha256:13808f76408ba29375dd78ea4442e36ede09b752034577ed8904b96a9468cfe6
raw payload included = false
secret included = false
elapsed wall time = approximately 65 seconds
D free after validation = approximately 53.23 GiB
```

Earlier image calls timed out at 30, 180, and 420 seconds before bounded generation was added. The new bounded result proves the unified local image path is callable on this CPU-only host. It does not prove semantic accuracy or production calibration.

DashScope after credential correction:

```text
DASHSCOPE_API_KEY current process = present
real compatible-mode request = HTTP 200
model = qwen-plus
A2 unified Provider Gateway status = completed
structured output hash present = true
response hash present = true
logical call ID present = true
response body = redacted
credential value = never printed or persisted
```

PostgreSQL:

```text
POSTGRES_DSN process = missing
POSTGRES_DSN user = missing
psql = missing
docker = missing
```

## Microscopic simulations

### Micro 1 - bounded local image capability

The unified gateway sent text plus a content-hashed PNG to the real local `qwen3-vl:4b` runtime with `num_predict=8`, zero temperature, and a 420-second deadline. The call completed and returned only a response hash and operational provenance. A2 records `callable` and independently records `uncalibrated`; no release PASS can be derived from this smoke evidence.

### Micro 2 - governed replay and revocation

A valid A1 bundle and signed quality proof were evaluated with a normalized trust policy. Reordering issuer and tenant lists produced the same policy hash, replayed the same record, and made one total Provider call. Changing the revocation set returned fail-closed INCOMPLETE, did not persist a replacement decision, and made no second Provider call. Reconciliation with the proof hash revoked through a supplied complete policy also committed zero decision and outbox rows.

## A1/A2/A3 macroscopic simulations

### Macro 1 - authenticated evidence to governed release output

A1 produces an authenticated, scoped evidence bundle. A2 verifies authenticity, scope, completeness, immutable artifact provenance, quality proof, and trust policy before calling a provider-neutral Judge. A2 validates structured output, checks calibration/golden/disagreement/review gates, persists one fenced decision plus outbox record, and exposes reproducibility hashes. A3 renders that committed decision and provenance without recomputing the score.

### Macro 2 - local and cloud callable but not truth

A1 evidence is structurally valid. The local multimodal Provider and real Qwen cloud Provider are callable, and the cloud result passes A2's structured-output validator. Neither transport success is truth or sufficient calibration. A2 must still apply golden regression, disagreement analysis, trust policy, and review before PASS. A3 can display the A2 state but cannot override it.

## Validation

```text
Focused Round 11 tests: 52 passed
Bundle plus orchestrator tests: 93 passed
Full A2 suite: 344 passed
Generated fixtures: 56/56 matched
Python compilation: passed
git diff --check: passed
Real local bounded image smoke: completed, callable, uncalibrated
Real DashScope direct probe: HTTP 200
Real qwen-plus through A2 Provider Gateway: completed with structured-output hash
```

Only expected `jsonschema.RefResolver` deprecation warnings and Git line-ending notices appeared.

## Growth auditor

The growth auditor confirms:

- only A2-owned files are included;
- main, A1, A3, and strategy refs were fetched and reviewed;
- all 20 prior tasks were implemented or have exact external-blocker evidence and an offline substitute;
- two microscopic and two macroscopic simulations are documented;
- local model callability is not mislabeled as calibration;
- no credential value or private evidence content is included;
- commit, push, and remote-SHA equality must be recorded after staging this worklog.

## Exactly 20 narrow tasks for Round 12

1. Validate `model_digest` format in local smoke evidence and reject malformed non-empty digests.
2. Validate `content_hashes` as canonical SHA-256 values before emitting smoke evidence.
3. Add a test proving `invalid_response` is protocol-reachable but uncalibrated.
4. Add a test proving connection failure is unavailable and uncalibrated.
5. Add a smoke evidence duration bucket without exposing precise host timing.
6. Add a bounded maximum image byte limit to the Ollama smoke CLI.
7. Reject unsupported image suffixes before reading image bytes.
8. Add a subprocess test for `num_predict` values 0, 257, and non-integer input.
9. Add a subprocess test proving model options reach the Ollama adapter request body.
10. Add provider-gateway coverage showing caller model options cannot override base URL or credential reference.
11. Add CLI replay coverage for duplicate revoked lists normalizing to the same record.
12. Add CLI conflict coverage for a changed maximum review age.
13. Add reconciliation coverage for a revoked key supplied through a complete trust-policy object.
14. Add recovery-envelope tamper coverage for the stored normalized trust-policy hash.
15. Add a public schema for local Provider smoke evidence.
16. Validate completed, timeout, invalid-response, and unavailable fixtures against that schema.
17. Add a deterministic local image golden case with expected structured semantic fields.
18. Add local golden-regression gating that cannot mark smoke-only evidence calibrated.
19. Add a secret-safe Qwen credential fingerprint marker so probes rerun only after credential rotation.
20. Run PostgreSQL parity if a real DSN/service appears; otherwise repeat exact discovery evidence and execute SQLite fencing parity.
