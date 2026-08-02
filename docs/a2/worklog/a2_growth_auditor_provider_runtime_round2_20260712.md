# A2 Growth Auditor — Provider Runtime Round 2 (2026-07-12)

## Cross-lane synchronization audit

- `git fetch origin --prune` was attempted and failed: GitHub port 443 could not be reached after about 21 seconds.
- Newest locally available reviewed refs, without claiming a successful refresh:
  - `origin/main`: `5dbf4ee2ab4c0ea8568623899244070dce9f9ce4`
  - `origin/agent/a1-local-sdk-runner`: `c784163588e9e0839fe17c604f3285c42efe3661`
  - `origin/agent/a3-commercial-growth-round4`: `2250254bfeeb8d9c24008c997296bf62b2e846a3`
  - A2 baseline `origin/dev/g3-a2-calibration`: `2117424da7cff97ff3acfb27ed9ef23bc3b1858f`
- Main strategy Bus re-reviewed: A2 owns configurable/versioned/auditable/costed judge service, async-model-provider direction, semantic evaluation, calibration, cost/risk policy, and bundle verification correctness.
- A1 authenticated bundle v2 reviewed: HMAC SHA-256, strict contract, tenant/project digests, evidence digest, validity window, and tamper/scope rejection.
- A3 release provenance v1 reviewed: five-field scope, read-only consumption, A2 release authority, broken-reference blocking, no A2 recomputation.
- Only A2-owned judge service, A2 schemas, A2 tests, A2 script, and this A2 worklog are changed.

## Previous auditor task closure — exactly 20 items

1. Normalized provider request Schema: implemented.
2. Normalized provider response Schema: implemented.
3. Model Registry record and lifecycle: implemented.
4. Registry capability filtering tests: implemented.
5. Ollama `/api/tags` discovery: implemented.
6. Ollama health probe with timeout/unavailable states: implemented.
7. Opt-in local Ollama text smoke command: implemented; runtime blocked because Ollama is not installed.
8. Opt-in local Ollama image smoke command with hash-only evidence: implemented; runtime blocked because Ollama is not installed.
9. Shared OpenAI-compatible adapter: implemented with normalized response and 429/5xx classification.
10. Credential resolver boundary: implemented; secrets resolve only inside the adapter.
11. Tenant provider/model allowlist: implemented.
12. Data-residency enforcement: implemented.
13. Per-modality and total payload limits: implemented.
14. Deterministic budget estimation/reservation: implemented.
15. Bounded retry policy: implemented for explicit retryable states only.
16. Timeout/circuit-breaker contracts: implemented.
17. Per-attempt token/cost ledger: implemented without raw payload.
18. Semantic judge structured-output validation: implemented with strict fields and abstain rules.
19. A3 public provider provenance handoff: implemented with five-field scope and `release_authority=false`.
20. Authenticated A1 evidence-bundle gate: implemented against A1 v2 HMAC/scope/digest/time semantics.

## Four simulation passes

### Microscopic pass 1 — happy path and controls

- Local-first Model Registry selects modality-capable active models.
- Tenant provider/model/residency/payload policy authorizes only explicit routes.
- Budget reservation and settlement create public-safe cost events.
- A timeout followed by a valid structured response succeeds only on the bounded second attempt.

### Microscopic pass 2 — adversarial failures

- Unknown credential references, oversized payloads, disallowed providers/models/regions, malformed semantic JSON, unknown fields, invalid scores, pass+abstain, and open circuits all fail closed.
- Authenticated bundle tampering, cross-scope use, expiration, and signature mismatch fail before Provider authorization.

### Macroscopic A1/A2/A3 pass 1 — authenticated trusted spine

- A1 `releasefoundry.a1.authenticated_evidence_bundle.v2` manifest is verified before A2 Provider provenance can become ready.
- A2 binds snapshot, logical call, response hash, authenticated bundle digest, provider/model, and five-field scope.
- Missing authentication or incomplete scope blocks the handoff.

### Macroscopic A1/A2/A3 pass 2 — authority and public safety

- Provider completion plus valid semantic JSON yields only `evaluation_eligible=true`.
- Every handoff has `release_authority=false` and names `a2.release_gate.v1` as decision authority.
- A3 receives hashes, blockers, and provenance only; no raw payload, secret, or authority to recompute A2 release policy.

## Verification evidence

- Focused Provider Gateway + Runtime tests: `17/17` passed, including JSON Schema validation for registry, semantic output, and ready/blocked A3 handoffs.
- Generated fixture check: `56/56` matched committed output.
- Full A2 suite: `185/185` passed.
- Python compile check for gateway/runtime/smoke CLI: passed.
- Ollama image smoke now uses protocol-compatible base64 while persisted smoke evidence retains only the SHA-256 of the original image bytes.
- Local environment probe: `ollama` executable not found; `127.0.0.1:11434/api/tags` unavailable. No real Ollama inference is claimed.
- No official ReleaseFoundry API key was read or used.
- OpenAI-compatible adapter is contract-tested without a live cloud credential; live OpenAI/Anthropic/Google calls are not claimed.

## Commit and push audit

- Commit: verified by the containing commit with subject `feat(a2): add governed provider runtime and model registry`.
- Push: must be verified after commit by comparing local HEAD with `refs/heads/dev/g3-a2-calibration`; a network failure must be reported rather than treated as success.

## Exactly 20 next-round narrow tasks

1. Add strict API idempotency conflict detection separate from content-addressed logical call IDs.
2. Add an async transport protocol while retaining the synchronous compatibility adapter.
3. Add async Ollama discovery and invocation tests with a local fake HTTP server.
4. Add async OpenAI-compatible invocation tests with a local fake HTTP server.
5. Add native OpenAI Responses protocol request/response normalization.
6. Add native Anthropic Messages protocol request/response normalization.
7. Add native Google GenerateContent protocol request/response normalization.
8. Add provider capability-cache TTL and stale-state semantics.
9. Add Model Registry provenance for discovery source and discovered timestamp.
10. Add model license and deployment-policy metadata for local open-source models.
11. Add a hardware probe contract for CPU, RAM, GPU, VRAM, and available disk.
12. Add a local-model tier planner for deterministic, lightweight, high-quality, and cloud-calibration tiers.
13. Add audio preprocessing artifact contracts with transcript hashes and timestamps.
14. Add file preprocessing artifact contracts with MIME, OCR/parser, and chunk hashes.
15. Add video preprocessing artifact contracts with frame/audio/timeline hashes.
16. Add durable audit-outbox records and replay tests for Provider authorization events.
17. Add strict persisted/transient response separation with redaction before storage.
18. Add disagreement analysis across deterministic, local-model, cloud-model, and human labels.
19. Add golden-regression eligibility that blocks uncalibrated semantic models.
20. Add a service-wrapper/OpenAPI route for authenticated Provider evaluation without exposing credentials.
