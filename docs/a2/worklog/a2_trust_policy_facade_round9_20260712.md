# A2 trust-policy facade and runtime safety — Round 9 — 2026-07-12

## Scope

This round changes only A2-owned files. A2 remains the sole release-decision
authority: A1 supplies authenticated evidence, and A3 consumes A2 decision and
provenance without recomputing a score or release state.

## Cross-lane synchronization and review

The fetch completed successfully on 2026-07-12:

```text
origin/main = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a1-local-sdk-runner = d1578bfa13a26456b3e110fdb372f713cad99beb
origin/codex/a3-commercial-growth-round4 = ccf6ce57890aaceabcb627c14d2e078674bd50ad
origin/codex/a3-main-contract-alignment-v2 = 45bec48e65f3ae11f0252174990365eb20e46ef6
```

`origin/codex/a3-main-contract-alignment-v2` advanced from `d4edf48` to
`45bec48`. Its request-boundary audit explicitly preserves A1 identity
authority, A2 Decision Ledger/release authority, and A3 route/RBAC/audit
ownership. No A2 contract conflict was found.

`origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` was reviewed.
It continues to require provider-independent A2 operation, Ollama and
OpenAI-compatible support, fail-closed provider failures, comparable
provenance, and no A3 decision recomputation. This round remains aligned.

## Delivered

- Normalized the evaluation trust policy at the public facade boundary.
- Exposed its canonical hash as
  `reproducibility.evaluation_trust_policy_hash`.
- Added the hash to the public bundle-evaluation schema.
- Added real CLI end-to-end coverage proving a valid policy reaches the HTTP
  Provider and an invalid policy fails before any Provider request.
- Bounded revoked key IDs to a public-safe 1–128 character format.
- Documented and tested empty issuer allowlist semantics.
- Tested tenant-list deduplication and deterministic normalization.
- Tested a review timestamp exactly one millisecond in the future.
- Added remote-completion reconciliation coverage proving a changed revocation
  policy cannot commit against the reserved request identity.
- Added reviewer tenant-salt rotation provenance guidance.
- Added Ollama installer `-DryRun`, with no download, writes, extraction or
  environment mutation; an actual PowerShell dry run succeeded.

## Prior 20-task disposition

1. **Done:** remote-completion reconciliation plus proof-key revocation change
   raises an idempotency conflict and commits no decision/outbox row.
2. **Done:** valid CLI trust-policy file reaches a stubbed real HTTP adapter.
3. **Done:** invalid CLI trust-policy file is rejected with zero HTTP calls.
4. **Done:** facade reproducibility includes the normalized policy hash.
5. **Done:** public bundle-evaluation schema requires that hash field.
6. **Done:** empty allowlist semantics are documented and tested.
7. **Done:** revoked key IDs use a bounded public-safe format in code/schema.
8. **Done:** duplicate tenant normalization is covered.
9. **Done:** future reviewer receipt at `NOW + 1 ms` blocks as stale.
10. **Done:** tenant-salt rotation provenance guidance was added.
11. **Done:** installer static ordering proves dry run precedes side effects.
12. **Done:** executable installer dry-run mode performs no side effects.
13. **Blocked externally:** no authoritative archive/checksum was guessed.
    Offline substitute: checksum remains mandatory and dry-run is executable.
14. **Blocked externally:** installation awaits authoritative archive metadata.
    Offline substitute: D-drive path/capacity/checksum gates are implemented.
15. **Blocked externally:** Ollama is absent, so no model was pulled.
    D drive has 58.22 GiB free and the 20 GiB safety threshold remains enforced.
16. **Blocked externally:** Ollama is absent. Offline substitute: unified
    gateway HTTP and deterministic fake-provider tests execute the same Judge
    validation path.
17. **Blocked externally:** Ollama is absent. Offline substitute: multimodal
    qualified/unqualified image evidence tests remain in the full A2 suite.
18. **Blocked externally:** `DASHSCOPE_API_KEY` and `QWEN_API_KEY` are absent
    at both process and user scopes. Offline substitute: Qwen-compatible CLI
    preset and OpenAI-compatible HTTP protocol tests pass.
19. **Blocked externally:** no local/Qwen pair exists, so a truthful signed
    disagreement receipt cannot be produced. Existing signed disagreement and
    reviewer-receipt paths remain tested.
20. **Blocked externally:** `POSTGRES_DSN`, `psql`, and Docker are absent.
    Offline substitute: SQLite recovery, fencing, reconciliation and atomicity
    tests pass.

## External capability evidence

```text
DASHSCOPE_API_KEY process=missing user=missing
QWEN_API_KEY process=missing user=missing
A1_EVIDENCE_HMAC_KEY process=missing user=missing
POSTGRES_DSN process=missing user=missing
ollama=missing
psql=missing
docker=missing
C_FREE_GIB=2.30
D_FREE_GIB=58.22
```

No live Qwen, Ollama, model installation, or PostgreSQL result is claimed.

The executable dry run reported:

```text
DRY_RUN=true
INSTALL_ROOT=D:\Ashr\ollama
MODEL_ROOT=D:\Ashr\ollama-models
DRYRUN_EXIT=0
```

The URL was intentionally non-routable; successful completion proves no
network request was attempted in dry-run mode.

## Microscopic simulations

### Micro 1 — invalid trust policy

Input: a valid signed A1 bundle plus a policy containing revoked key ID
`contains whitespace`.

Simulation: CLI parses and normalizes policy before credential resolution,
database creation, gateway execution, or HTTP invocation.

Observed: non-zero exit, stable validation error, Provider call count `0`.
Result cannot become PASS.

### Micro 2 — changed revocation state during reconciliation

Input: an operation interrupted after Provider-call authorization, followed by
a remote-completed observation while the reconciler supplies a newly revoked
quality-proof key.

Simulation: the changed policy changes the governed request identity.

Observed: `IdempotencyConflictError`; zero release-decision and outbox rows.
Remote success cannot bypass the policy version reserved before the call.

## A1/A2/A3 macroscopic simulations

### Macro 1 — authenticated evidence to governed PASS

A1 emits a tenant/project-scoped authenticated bundle and signed quality proof.
A2 verifies authenticity, scope, integrity and completeness, invokes the
provider-neutral Judge, validates structured output, applies trust/release
policy, commits the Decision Ledger record, and exposes the policy hash.
A3 reads only A2's committed decision/provenance. Result: PASS is possible only
after persistence; A3 performs no recomputation.

### Macro 2 — policy or Provider failure

A1 evidence is valid, but either the trust policy is invalid/revoked or the
Provider times out/fails. A2 rejects invalid policy before invocation, or
records the Provider failure and returns BLOCK. No release-ready decision is
emitted. A3 displays A2's blocking state and provenance only. Neither a remote
completion nor a UI calculation can manufacture PASS.

## Validation

```text
Focused bundle/orchestrator tests: 77 passed
Full A2 suite: 325 passed
Generated fixtures: 56/56 matched
Python compilation: passed
git diff --check: passed
PowerShell installer dry run: passed
```

Only expected `jsonschema.RefResolver` deprecation warnings were emitted.

## Growth auditor

The auditor confirms that this round has A2-owned code, schema, tests,
documentation and executable evidence ready for explicit staging. Commit,
push and remote-SHA equality are checked after this document is written.

## Exactly 20 narrow tasks for Round 10

1. Add schema validation coverage for the facade's structured INCOMPLETE path.
2. Reject boolean `reviewed_at_unix_ms` values as invalid receipts.
3. Add revoked key ID minimum/maximum boundary tests at 1 and 128 characters.
4. Add rejected revoked key ID tests at 129 characters and leading punctuation.
5. Bind trust-policy hash into a CLI-produced replay comparison assertion.
6. Add CLI malformed JSON trust-policy error sanitization coverage.
7. Add CLI missing trust-policy file fail-before-provider coverage.
8. Add remote-completion reconciliation coverage for revoked proof hashes.
9. Add recovery coverage for a normalized duplicate-policy input.
10. Add an installer dry-run assertion that no target directory is created.
11. Add installer rejection coverage for a non-D install root.
12. Add installer rejection coverage for a non-D model root.
13. Add installer checksum-mismatch cleanup coverage using a local test archive.
14. Discover and record an authoritative Ollama Windows artifact URL/checksum.
15. Install Ollama to D only if the artifact is authoritative and D stays above 20 GiB.
16. Pull one lightweight text/vision model only if D stays above 20 GiB.
17. Run unified-gateway local text and image smoke on one evidence snapshot.
18. Run Qwen text/image smoke when inherited `DASHSCOPE_API_KEY` is present.
19. Persist a signed local-versus-Qwen disagreement receipt when both runs exist.
20. Run PostgreSQL recovery/fencing parity when `POSTGRES_DSN` or CI service exists.
