# A2 multimodal repair, fallback binding, and latency governance - Round 15 - 2026-07-12

## Scope and authority

Only A2-owned calibration, schemas, fixtures, tests, and this worklog change. A1 remains evidence producer; A2 remains the sole evaluation and release-decision authority; A3 consumes the exact committed decision without recomputation. Model output, deterministic repair, fallback availability, and low latency are observations, not truth or PASS authority.

## Cross-lane synchronization

The Round 15 fetch attempt failed exactly:

```text
Failed to connect to github.com:443 after 21063 ms
```

No fresh refs are claimed. Locally available and reviewed:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = f9562494d427c430c043c4316d91eb2510df62a1
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = c8420813ed6cb94535bd108b30bd97663b906bdb
origin/main strategy blob = 575b31b80981542fc96f9a9310e66a9318974abb
```

The strategy still requires Provider-neutral, fail-closed A2 and forbids A3 decision recomputation. A1's restart-safe delivery and A3's sealed Golden tool chain remain compatible with A2's immutable evaluation identity and exact committed-decision consumption.

## Delivered and prior 20-task disposition

1. **Done:** semantic-disagreement review-packet schema.
2. **Done:** deterministic review packet schema validation.
3. **Done:** Provider fallback evaluation schema.
4. **Done:** blocked and review-available fallback schema validation.
5. **Done:** exact primary/fallback provider-model-version bindings.
6. **Done:** absent runtime bindings block review availability.
7. **Done:** fallback calibration binds prompt, options, and artifact hashes.
8. **Done:** changed generation-options hash blocks calibration reuse.
9. **Done:** explicit structured-output repair governance state.
10. **Done:** original and repaired hashes are separately retained.
11. **Done:** missing fields remain blocked without repair policy.
12. **Done:** safety field severity and missing-safety blocker.
13. **Done:** exact LLaVA candidate fixture remains uncalibrated.
14. **Done:** real LLaVA probe states schema in prompt and validates locally.
15. **Done:** repeated probe produced equal output hashes and recorded latency.
16. **Done:** resource observation includes installed bytes, wall time, and tokens.
17. **Done:** excessive latency yields `incomplete`, never PASS.
18. **Externally blocked with substitute:** PostgreSQL tools/DSN absent; full SQLite-backed A2 suite executed.
19. **Done:** A1 replay under rotated Provider credentials preserves A2 semantic evaluation identity.
20. **Done:** exact A3 consumption succeeds; recomputed release state is rejected.

## Real LLaVA evidence

```text
model = llava:7b
model digest = sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081
installed bytes = 4,733,363,377
artifact hash = sha256:4f5cf36d805b1017209e9c49a344e3fb68ae79b678f42ef40340b1ba197ee69a
prompt hash = sha256:028633a88e903354e1992968cf08e028baf977f228d2843242144dc93ef5f1be
output hash, run 1 = sha256:7a8dda6444d97fa5ae7b0b7b9c45054315b63507176fa762b3291cc3a6cc5fcb
output hash, run 2 = sha256:7a8dda6444d97fa5ae7b0b7b9c45054315b63507176fa762b3291cc3a6cc5fcb
cold wall time = 58.435 seconds
warm wall time = 5.176 seconds
prompt tokens = 715
completion tokens = 27
```

Both runs returned schema-valid public JSON:

```json
{"contains_text": true, "primary_color": "blue", "safety_risk": "unknown"}
```

Repeatability is promising but does not establish truth or calibration. `safety_risk=unknown` still requires review. Under a 30-second latency policy the cold run is `INCOMPLETE`; the warm run is within limit. The candidate fixture explicitly remains `golden_eligible=false`.

## PostgreSQL discovery

```text
POSTGRES_DSN = absent
psql = absent
docker = absent
```

SQLite verifies executable persistence/fencing behavior but is not PostgreSQL parity evidence.

## Microscopic simulations

### Micro 1 - deterministic repair cannot silently create truth

LLaVA omits `safety_risk`. With no repair policy, output remains blocked. With an explicit deterministic default, A2 retains both original and repaired hashes, marks `semantic_observation_modified=true`, keeps calibration `uncalibrated`, requires human review, and grants no release authority.

### Micro 2 - calibrated fallback options change

A fallback previously passed Golden calibration for one prompt/options/artifact binding. Runtime changes only the options hash. A2 detects the mismatch, blocks review availability, and cannot reuse the old calibration despite successful transport and parseable output.

## A1/A2/A3 macroscopic simulations

### Macro 1 - A1 replay and credential rotation

A1 replays the same immutable evidence snapshot after a Provider credential rotates. Provider call identity changes to avoid stale authentication cache, but A2 semantic evaluation identity remains derived only from evidence, policy, and Golden suite. A2 produces one traceable semantic decision identity, while retaining both operational attempts.

### Macro 2 - reviewed disagreement consumed by A3

A2 creates a bound disagreement receipt, review packet, human-reviewed result, and committed decision hash. A3 consumes that exact hash successfully. If A3 supplies a recomputed score, policy result, status, or release authority, A2's consumption validator rejects it as `a3_recomputed_release_state_forbidden`.

## Validation

```text
Focused Round 15 tests = 50 passed
Full A2 suite in sandbox = 379 passed, 1 filesystem permission error
Filesystem-dependent checksum test with approved D:\Ashr access = 1 passed
Effective full A2 result = 380 passed
Generated fixtures = 56/56 matched
git diff --check = passed
```

## Growth auditor

The auditor confirms A2-only ownership, exact blocker evidence, all 20 tasks disposed, two microscopic and two macroscopic simulations, fail-closed repair/fallback/latency behavior, uncalibrated LLaVA status, no A3 recomputation, no secret/private-ref content, and requires explicit staging, commit, push, and SHA verification.

## Exactly 20 narrow tasks for Round 16

1. Add a structured-output repair JSON schema.
2. Validate blocked, not-required, and repaired-for-review states.
3. Add a local-resource-observation JSON schema.
4. Validate within-limit and incomplete latency observations.
5. Add an A3 decision-consumption validation schema.
6. Validate accepted and recomputation-rejected A3 consumption.
7. Bind repair policy to an immutable policy hash.
8. Reject repaired-output replay under a changed repair-policy hash.
9. Forbid deterministic defaults for safety fields unless value is `unknown`.
10. Require reviewer identity hash before repaired output can enter calibration.
11. Add cold-start and warm-start latency classes.
12. Prevent warm latency from concealing a cold-start SLO failure.
13. Add local memory/resource telemetry when Ollama exposes it.
14. Run three additional warm LLaVA probes and measure output-hash stability.
15. Run one adversarial image prompt-injection fixture through LLaVA.
16. Prove image text cannot override the governed output schema or release policy.
17. Recheck PostgreSQL and otherwise rerun SQLite recovery/fencing evidence.
18. Retry fresh main/A1/A3 synchronization and review any changed refs.
19. Simulate repaired local output disagreeing with governed cloud output.
20. Simulate A3 displaying an INCOMPLETE cold-start latency decision without upgrading it.
