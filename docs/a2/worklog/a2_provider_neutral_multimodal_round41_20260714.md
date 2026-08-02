# A2 Round 41 — provider-neutral multimodal conformance

Date: 2026-07-14
Branch: `dev/g3-a2-calibration`

## Scope and reviewed refs

Only A2-owned files changed. The round fetched and reviewed:

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a1-local-sdk-runner`: `23072311c80395989adaba1bd164265bd67517b1`
- `origin/agent/a3-main-contract-alignment-v2`: `8bcbd3a60b8b35366267bee5d45f2f031e811eb9`
- `origin/dev/g3-a2-calibration`: `0712db7c18a2310b7e3ade928e618c99a74f8933`
- `origin/main:docs/strategy`: `d0d5d4f25e5f11ff0ef64fac2f8de0cfbf96eb3a`

Strategy remains provider-neutral and fail-closed: A1 supplies evidence, A2 owns the only release decision, and A3 consumes provenance and decisions without recomputation. Local and cloud providers remain fallible evidence sources rather than truth.

## Round 40 task disposition

1. Added a generic `OpenAICompatibleMultimodalAdapter`.
2. Moved DashScope endpoint and credential selection behind the provider registry.
3. Added image MIME, structured-output, retry-class, token-bound, and local/cloud capability discovery.
4. Added one provider conformance receipt schema shared by cloud, offline, and local adapters.
5. Reused the generic adapter for the real DashScope endpoint; the key was resolved only at the adapter boundary.
6. Added deterministic valid, invalid, timeout, and rate-limit offline states.
7. Added separate parse-retry and transport-retry policies.
8. Added total-attempt latency and final-attempt latency as separate v5 metrics.
9. Added per-taxonomy Wilson lower-bound policy enforcement.
10. Added a versioned policy schema and canonical policy hash.
11. Bound v5 evidence to manifest and ordered case-plan hashes.
12. Added JPEG MIME preservation and structured-output transport regression coverage.
13. Added a comparison-receipt verification schema and builder validation.
14. Added a real-review builder that fixes identity class to `human_reviewer`.
15. Added predecessor chaining, sequence numbers, duplicate-disposition rejection, and broken-chain rejection.
16. Attempted the full local Round 40 matrix, bounded it after five 75-second timeouts, then completed a correct-version two-case probe.
17. Probed `POSTGRES_DSN`, `psql`, Docker, standard PostgreSQL paths, and services. No real PostgreSQL runtime was available; the offline persistence substitute passed 29 tests.
18. Rechecked exact A1/A2/A3 candidate binding. It is absent, so no Trusted Spine was generated.
19. Re-ran both Qwen cloud models only on the two aggregate-internally-unstable cases.
20. Re-fetched refs and completed the required simulations, growth audit, tests, fixture check, CL gates, diff check, explicit staging, commit/push, and SHA checks as closing gates.

## Provider-neutral implementation

The registry now describes `dashscope`, `dashscope-international`, `offline-deterministic`, and `ollama-local` without exposing credentials. The generic OpenAI-compatible adapter resolves the credential reference only at invocation time and classifies authentication, rate-limit, server, timeout, malformed-envelope, and transport failures. Provider capability hashes cover protocol, MIME types, structured output, retry classes, token bound, and locality.

DashScope calibration moved to schema v5 while v4 remains byte-for-byte frozen for historical evidence. V5 adds provider capability, manifest, ordered plan, and policy hashes; per-taxonomy Wilson lower-bound gates; and separate final-attempt latency. The versioned policy fixture is non-authoritative and public-safe.

The real DashScope credential was verified through the generic OpenAI-compatible endpoint with HTTP 200 and a non-empty model catalog. No key, bearer header, raw response payload, or signed URL was persisted.

## Real cloud observations

The two cases previously classified as aggregate `internally_unstable` were repeated three times per model:

- `qwen-vl-plus`: 6 eligible attack observations, sensitivity `0.333333`, Wilson 95% `[0.096769, 0.700012]`, p95 `1.081 s`, BLOCKED.
- `qwen-vl-max`: 6 eligible attack observations, sensitivity `0.0`, Wilson 95% `[0.0, 0.390343]`, p95 `1.774 s`, BLOCKED.

Repeat comparison produced 4 agreements and 2 semantic disagreements. Both case aggregates remained internally unstable and generated human-review queue receipts. Attack-only diagnostics intentionally contain no safe sample, so missing-safe-sample and specificity blockers are expected limitations, not provider transport failures. Neither provider is promotable or authoritative.

## Local Ollama observations

The installed runtime is Ollama `0.31.2`; `qwen3-vl:4b` is bound to model-layer digest `sha256:9c60bdd691c1897bbfe5ddbc67336848e18c346b7ee2ab8541b135f208e5bb38`.

The original full Round 40 attempt was stopped after five 75-second timeouts. Its CLI declared `0.11.4` and used a short, non-schema model identifier, so that historical partial journal is retained only as failed diagnostic evidence and is explicitly rejected as a qualification binding.

A corrected two-case, one-repeat, `json_schema`, 128-token probe completed both requests in `7.563 s` and `7.997 s`. Both returned empty structured content, leaving zero eligible observations. The local provider therefore remains BLOCKED for invalid structured output and insufficient safe/attack sample counts. Faster transport does not make the judge reliable.

## PostgreSQL and Trusted Spine

The round found no `POSTGRES_DSN`, `psql`, Docker runtime, local PostgreSQL installation, or PostgreSQL service. Same-round real PostgreSQL persistence proof remains BLOCKED. The offline durability substitute covered JSONL atomic replacement, file fsync, manifest reopen verification, and replay/rollback/fork detection.

A1's current branch is `23072311...`, but its Round 62 receipt binds `round62-source-candidate` to `5dd6a898...`. A2 has no shared candidate ID, while A3 requests `a3-golden-20260712-002` at `8bcbd3a...`. Because these are not one exact candidate binding, A2 generated a blocker receipt rather than a Trusted Spine.

## Microscopic simulations (exactly 2)

1. A generic OpenAI-compatible provider returns valid JSON once, then timeout and rate-limit failures. Credential resolution occurs only at the adapter boundary; failure states remain ineligible, the conformance receipt records them, and none can become PASS.
2. A reviewer submits a second disposition with a broken predecessor hash or repeats the same disposition for the same queue receipt. The real-review builder rejects both before emitting a receipt; a valid second review must hash-chain to the first and receive sequence 2.

## A1/A2/A3 macroscopic simulations (exactly 2)

1. A1 submits a complete multimodal evidence bundle. Qwen cloud judges disagree and remain internally unstable, while the local judge returns invalid structured output. A2 emits BLOCK and human-review receipts; A3 may display them but cannot recompute or promote the candidate.
2. A1's receipt SHA, A2's current base SHA, and A3's requested candidate are all individually traceable but do not identify one exact candidate. A2 refuses Trusted Spine generation, and A3 must render incomplete provenance rather than treating an older ledger as current authority.

## Growth auditor

The growth auditor confirms all 20 Round 41 tasks have code, schema-valid evidence, tests, or an explicit fail-closed blocker. Growth came from a provider-neutral transport contract, capability hashes, policy and plan binding, real cloud reruns, corrected local runtime binding, receipt verification, and human-review chaining. It did not come from counting more provider names or treating a model output as truth.

Verification completed before closing:

- A2 suite: `525 passed`, `1120 subtests passed`.
- PostgreSQL offline persistence subset: `29 passed`.
- Generated fixtures: all 56 matched.
- CL hygiene: passed.
- CL commercial: passed.
- `git diff --check`: passed.
- Secret scan, explicit A2-only staging, commit/push, remote SHA equality, and clean worktree are final mechanical gates.

## Round 42 narrow tasks (exactly 20)

1. Add a provider-neutral parsed-response contract shared by DashScope and Ollama.
2. Capture Ollama thinking/content fields separately so empty content cannot hide generated reasoning.
3. Add a local structured-output recovery probe with parse retry bounded to one retry.
4. Add an Ollama adapter conformance test for HTTP timeout and malformed envelopes.
5. Add provider conformance receipt source-evidence hashes.
6. Add conformance receipt predecessor chaining across provider versions.
7. Add policy-hash mismatch rejection when resuming a cloud calibration.
8. Add ordered-case-plan mismatch rejection before any provider call.
9. Add a minimum per-taxonomy Wilson sample-size policy.
10. Add confidence-interval reporting for specificity on an expanded safe-control set.
11. Add at least five deterministic safe local controls without text.
12. Add at least five deterministic attack controls spanning three taxonomies.
13. Run the expanded bounded matrix on `qwen3-vl:4b`.
14. Run the same bounded matrix on `llava:7b` for comparative diagnostics.
15. Compare local provider disagreement without assigning either model truth status.
16. Add a human-review receipt verification command for predecessor chains.
17. Add a PostgreSQL proof launcher that accepts a temporary local DSN without persisting credentials.
18. Re-run the real PostgreSQL proof if a DSN becomes available; otherwise refresh blocker evidence.
19. Recheck exact A1/A2/A3 candidate binding and generate no Trusted Spine unless all identifiers match.
20. Re-fetch refs, run exactly 2 micro and 2 macro simulations, growth audit, all A2 tests, fixtures, both CL gates, explicit commit/push, and SHA equality.
