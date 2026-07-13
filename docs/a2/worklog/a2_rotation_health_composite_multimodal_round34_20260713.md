# A2 rotation, health, composite multimodal, and calibration governance — Round 34 (2026-07-13)

## Synchronization and cross-project review

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = 23072311c80395989adaba1bd164265bd67517b1
origin/codex/a3-main-contract-alignment-v2 = ddd4d04ec53a7c4524eda2e028493bbe613b6ff0
origin/main:docs/strategy = d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a
```

Fresh fetch succeeded. Main and A1 did not move. A3 advanced from `8a92d4169ae0da96247be679146dd0f027031a59` to `ddd4d04ec53a7c4524eda2e028493bbe613b6ff0` and added same-candidate integrity/deployment handoff. The review confirms the intended boundary: A3 verifies and displays bindings and the committed A2 decision; it must not recompute the release result. A2 therefore continues to bind evidence, model/provider identities, policy, calibration, persistence, and the sole release decision.

## Round 34 disposition

1. Provider receipt key policies now validate rotation overlap and handoff gaps.
2. Duplicate `(issuer, key_id)` records are rejected as ambiguous.
3. Ed25519 adapters share one canonical signed-receipt byte representation, including Unicode and nested-key vectors.
4. Persistent replay snapshots bind sequence number and predecessor hash.
5. Crash injection after temporary-file fsync and before replace proves that the prior valid replay snapshot survives.
6. Replay locking has a bounded wait and returns `provider_receipt_replay_lock_timeout` fail closed.
7. Runtime recovery validates health payload field coverage, semantic status, schema version, and runtime-version hash.
8. Runtime recovery emits the governed health compatibility-policy hash.
9. Windows volume API failures are reduced to stable public-safe classes; raw OS text and raw identifiers are not exposed.
10. JSONL durability receipts separate file write, file fsync, atomic replace, reopen, and parent-directory flush. File fsync remains honestly `not_exposed`; full durability is not claimed.
11. Legacy empty taxonomy-policy identity can be migrated only through an explicit governed helper.
12. Taxonomy policy has an allowlist and unknown taxonomy classes fail closed.
13. Added three deterministic text-free safe controls with exact semantic labels and byte hashes.
14. Added one positive and one negative public-safe example for each of five governed taxonomy classes.
15. External photographic provenance now enforces retrieval freshness, maximum age, and future-timestamp blocking.
16. A real Ollama runtime is available at `D:\Apps\Ollama\ollama.exe`; version `0.31.2`, executable SHA-256 `908a873f73c4176959b7ef4e3b2f3abb01f8526fc32c49e73ca4f058faa16578`.
17. Real model discovery observed `llava:7b` digest `8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081` and `qwen3-vl:4b` digest `1343d82ebee38e26a4dd6b0180b915eb91550184e67c505dea97509571c8f683`. A Qwen3-VL smoke with 256 output tokens remained fail closed in governed JSON mode; direct public-content diagnosis showed that a response may appear with a larger budget, but repeated plain-mode output was not consistently valid JSON. Private reasoning was never promoted.
18. Same-round PostgreSQL proof remains unavailable: `POSTGRES_DSN_PRESENT=False`, `PSQL_PRESENT=False`, `DOCKER_PRESENT=False`. Offline persistence/manifests and their tests remain the honest substitute, not a database proof.
19. Trusted Spine remains deferred because the exact final cross-project A1/A2/A3 candidate SHAs, final run results, and grades do not yet form one authoritative candidate.
20. Added a composite-agent capability contract for an agent/planner that delegates image generation or image-plus-text rendering. Planner and image model identities are separate; generated artifacts require hashing, text rendering requires OCR comparison, an independent safety judge is required, and self-evaluation has no release authority.

The representative labels `gpt-5.6-sol` and `image-2` in tests are user-provided identities used to exercise the contract; this round does not independently assert product availability or undocumented provider behavior.

## Real multimodal observations

The official smoke command can now be launched directly from outside the repository package context because the A2 script resolves the repository root before importing `services`.

```text
model = qwen3-vl:4b
image_hash = sha256:bf48de23739ac84a83feb4bb77f6c91d264a0f06b6227e4ad77406a7fba37845
num_predict = 256
official_smoke_status = invalid_response
capability_state = protocol_reachable
calibration_state = uncalibrated
duration_bucket = 1_to_5m
raw_payload_included = false
```

A direct public-safe diagnostic with the same 256-token budget produced public content once in about 17 seconds and it was parseable JSON, while a repeated adapter plain-mode diagnostic took about 28 seconds and produced non-JSON public content. This variance is evidence of an unstable output-mode/protocol contract, not evidence for promotion. The current candidate remains blocked pending a governed prompt/output-mode matrix, repeated runs, latency qualification, specificity, taxonomy coverage, and confidence bounds.

## Exactly two microscopic simulations

1. Two provider receipt keys overlap during a governed rotation, then a malformed policy reuses the same `(issuer, key_id)` and leaves a handoff gap. A2 accepts the explicitly permitted overlap but reports ambiguity and the handoff gap for the malformed policy; no receipt becomes verified from ambiguous key identity.
2. A text-free safe control is submitted to Qwen3-VL with a larger output budget. One invocation yields public JSON and a repeated invocation yields non-JSON public content. A2 hashes only public content, ignores private reasoning, marks malformed output non-promotable, and does not infer safety or release readiness from transport reachability.

## Exactly two A1/A2/A3 macroscopic simulations

1. A1 supplies authenticated evidence plus a signed provider receipt after worker recovery. A2 validates key rotation, canonical signature bytes, replay lineage, health payload compatibility, evidence completeness, Judge output, taxonomy policy, and persistence before committing the sole `PASS`, `BLOCK`, or `INCOMPLETE` decision. A3 binds that exact A1 run and A2 decision to its candidate and fails closed on any mismatch.
2. A1 supplies evidence from a composite agent whose planner delegates image and image-plus-text generation. A2 separately binds planner and delegated image-model identities, hashes generated artifacts, compares rendered text through OCR, invokes an independent safety judge, and applies calibration/latency/specificity gates. A3 displays the committed decision and provenance only; planner self-evaluation cannot authorize release.

## Growth auditor

The change set is limited to A2-owned Judge/runtime/persistence code, A2 schemas, A2 tests, public-safe deterministic fixtures, the A2 Ollama smoke script, and this worklog. It contains no credential, token, raw provider payload, private reference, restricted photographic bytes, or A1/A3 source edit. The real DashScope credential retained for future validation was neither read into the diff nor deleted. Commit and push are mandatory. Remaining gaps are stable governed Qwen3-VL structured output, larger per-taxonomy labeled sets and confidence bounds, interactive/CI-grade latency, same-round PostgreSQL proof, actual temporary-file fsync exposure, a production composite-agent invocation adapter, and the final SHA-matched Trusted Spine.

## Exactly 20 Round 35 tasks

1. Add a schema and fixture for Windows volume observation states and error classes.
2. Test Windows API false-return classification through dependency injection instead of platform-only execution.
3. Replace temporary `Path.write_bytes` in JSONL persistence with an explicitly flushed and fsynced file handle.
4. Add crash injection after file fsync and after atomic replace as separate durability stages.
5. Bind the durability receipt hash into release-decision provenance.
6. Add replay snapshot rollback detection across multiple valid but non-latest snapshots.
7. Add replay lock ownership diagnostics that remain public safe.
8. Add explicit taxonomy-policy allowlists to legacy policy fixtures instead of deriving them.
9. Add JSON schemas for deterministic safe-control expansion and balanced taxonomy controls.
10. Generate at least two more deterministic text-free controls with exact semantic labels and hashes.
11. Run a governed Qwen3-VL matrix across JSON/plain modes and 128/256-token budgets with repeated trials.
12. Record latency distributions rather than single-call duration buckets for Qwen3-VL.
13. Run the same safe/attack mini-suite on `llava:7b` and `qwen3-vl:4b` under identical bindings.
14. Require valid public structured output before any multimodal metric denominator is incremented.
15. Add composite-agent delegated-call receipts binding planner request, generated artifact, and image-model response.
16. Add OCR disagreement tests for generated image-plus-text artifacts.
17. Add independent safety-judge disagreement and human-review routing for composite agents.
18. Run real PostgreSQL persistence proof only if a safe DSN and client/server tooling are available; otherwise refresh exact blockers and offline substitute.
19. Refresh main, active A1/A3, strategy, and current A2 tracking refs immediately before commit; generate Trusted Spine only for one exact final candidate.
20. Run exactly two micro simulations, two macro simulations, growth audit, full A2 validation, fixture check, CL Gate, explicit staging, commit, push, and three-way SHA verification.
