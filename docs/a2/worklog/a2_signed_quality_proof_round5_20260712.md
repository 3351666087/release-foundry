# A2 signed evaluation quality proof — round 5

## Synchronized evidence

- `origin/main`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a1-local-sdk-runner`: `d1578bfa13a26456b3e110fdb372f713cad99beb`
- `origin/agent/a3-commercial-growth-round4`: `ccf6ce57890aaceabcb627c14d2e078674bd50ad`
- `origin/agent/a3-main-contract-alignment-v2`: `d4edf48cbc7faedcadd5c6f4921d2e4fd2c04d3d`
- Strategy reviewed: `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md`

A1 did not change the authenticated evidence bundle contract. The active A3 delta adds
trusted access, audit persistence and tenant isolation; it still consumes A2 authority
without recomputing release state. The A2 signed-proof direction remains aligned.

## Delivered slice

- Replaced caller-supplied quality assertions with an authenticated proof contract.
- Bound proof validity to five-field scope, authenticated A1 bundle, immutable evidence
  snapshot, Provider, model, model digest, prompt hash and policy version.
- Enforced validity window, strict fields, HMAC-SHA256 verification and content-addressed
  calibration evidence.
- Persisted only public-safe issuer and hash metadata; raw key material is never returned.
- Preserved fail-closed semantics: missing, expired, tampered or replayed proofs block
  release even when the Provider returns a passing score.
- Added a machine-readable JSON Schema and persistence recovery validation for v2 quality
  state.

HMAC is the current deployable symmetric-key boundary. An asymmetric signature adapter and
revocation registry remain necessary before cross-organization issuers are trusted.

## Real-provider and local-model evidence

- `DASHSCOPE_API_KEY`: missing from the inherited process environment.
- `QWEN_API_KEY`: missing from the inherited process environment.
- No live Qwen request was sent and no claim of live-model validation is made.
- Drive `C:` has 2.03 GB free; this is still insufficient for a safe Ollama install plus
  model pull.
- Drive `D:` has 58.22 GB free, so a later runtime/model relocation is feasible.
- Offline deterministic tests remain the non-model closure and signed proof tests use no
  external service.

## Microscopic simulations

- Micro A: A valid proof bound to `semantic-1` and policy v1 permits the otherwise passing semantic
   result to reach A2 `allow`.
- Micro B: The same signed bytes reused after changing model or policy produce
   `quality_proof_binding_mismatch`; Provider output cannot override the blocker.

## A1/A2/A3 macroscopic simulations

- Macro A: A1 supplies an authenticated bundle; A2 authenticates it, constructs a versioned
   snapshot, verifies a separately signed quality proof, calls the Judge, commits the
   ledger and exposes only public-safe proof hashes to A3.
- Macro B: A valid A1 bundle plus a passing Provider result but an expired or tampered quality
   proof produces A2 `BLOCK`; A3 receives `release_ready=false` and cannot recompute it.

## Growth auditor

Commit scope must contain only A2-owned files. Push completion must be verified by comparing
local HEAD with `refs/heads/dev/g3-a2-calibration`. Secret scanning must reject literal keys,
tokens, Bearer credentials and `docs/evidence/private_refs/`.

Exactly 20 narrow next tasks:

1. Add an Ed25519 evaluation-quality proof verifier.
2. Add issuer allowlist and tenant-scope authorization.
3. Add key revocation and proof revocation lookups.
4. Add maximum proof lifetime policy.
5. Bind a rubric version into signed proof fields.
6. Bind a golden dataset digest into signed proof fields.
7. Bind calibration metric thresholds into signed proof fields.
8. Persist signed-proof verification parity in PostgreSQL.
9. Add migration compatibility tests from quality state v1 to v2.
10. Add CLI loading for a signed quality proof JSON file.
11. Add CLI subprocess success tests for PASS exit code.
12. Add CLI subprocess success tests for BLOCK exit code.
13. Add CLI subprocess success tests for INCOMPLETE exit code.
14. Add a DashScope/Qwen OpenAI-compatible registry preset.
15. Run a Qwen text smoke when `DASHSCOPE_API_KEY` is inherited.
16. Run a Qwen vision smoke when `DASHSCOPE_API_KEY` is inherited.
17. Add a disk-capacity preflight with configurable model storage drive.
18. Install Ollama or an equivalent local runtime on `D:` after preflight.
19. Run one local vision model against the same immutable bundle as Qwen.
20. Persist deterministic-versus-semantic disagreement review disposition.
