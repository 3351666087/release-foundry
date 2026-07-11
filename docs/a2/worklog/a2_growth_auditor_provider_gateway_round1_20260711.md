# A2 Growth Auditor — Provider Gateway Round 1 (2026-07-11)

## Scope and branch evidence

- A2 branch: `dev/g3-a2-calibration`.
- Reviewed local remote refs after a fetch attempt: `origin/main=5dbf4ee`, `origin/codex/a1-local-sdk-runner=c784163`, `origin/codex/a3-commercial-growth-round4=2250254`, `origin/dev/g3-a2-calibration=8cd1d4f`.
- `git fetch origin --prune` was attempted this round and failed with `Recv failure: Connection was reset`; therefore these are the newest locally available remote refs, not a claim that the network remote was refreshed successfully.
- Main strategy bus reviewed: `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
- A1/A3 direction checked: A1 evidence remains upstream truth-bearing input; A2 owns snapshot/judge/release decisions; A3 consumes provenance and must not recompute A2 decisions.
- This round changes only A2-owned judge service, schema, tests, and A2 worklog files.

## Implementation audit

- Added a provider-independent `ProviderGateway` with explicit provider definitions and protocol adapters.
- Added tenant and immutable snapshot binding, capability selection, content hashes, payload hashes, and replay-safe logical call IDs.
- Calls fail closed for incomplete/cross-tenant evidence, audit failure, unsupported modality/protocol, invalid response, timeout, provider error, and invalid budget input.
- Audit authorization is written before the external adapter is invoked.
- Public result contracts exclude raw requests, raw responses, and secrets; cloud entries carry only `secret://` references.
- Added a minimal Ollama `/api/chat` text/image adapter and disabled-by-default cloud provider catalog entries.
- Provider output is not treated as truth: only a completed invocation is `evaluation_eligible`; every invocation explicitly carries `release_authority=false`, so only downstream judging, calibration, policy, and review can authorize release.

## Simulation evidence

### Microscopic simulation round 1

- Successful strict-fake call produced one audit event and one provider call.
- Identical replay returned the same result without a second provider call.
- Same client idempotency key with a changed payload or model produced a distinct logical call, preventing stale result aliasing.

### Microscopic simulation round 2

- Timeout, malformed normalized response, provider exception, unknown protocol, and audit writer failure all failed closed.
- Image bytes without `content_hash` and unsupported audio capability were rejected before provider execution.

### A1/A2/A3 macroscopic simulation round 1

- Incomplete A1 snapshot and cross-tenant snapshot never reached the provider adapter.
- Snapshot ID/hash, tenant, provider/model, modalities, and payload hash remain bound in the A2 invocation result.

### A1/A2/A3 macroscopic simulation round 2

- Every provider failure has `evaluation_eligible=false`, and successful calls still have `release_authority=false`; neither state can become an A2 release pass by itself.
- A3 can consume public status, blockers, hashes, and attempt provenance without raw evidence or secret material and without recomputing the A2 decision.

## Verification evidence

- Provider Gateway unit tests: `8/8` passed.
- Generated A2 fixtures: `56/56` matched committed output.
- Full A2 suite: `176/176` passed.
- Real Ollama smoke was not executed in this round.
- Cloud adapters are catalog/protocol placeholders only; this round does **not** claim that all cloud providers can already be called.
- Async transport, durable audit outbox, credential resolution, budget reservation, retry/circuit breaking, structured semantic-output validation, and full audio/file/video preprocessing remain open.

## Commit and push audit

- Commit: verified by this worklog's containing commit, subject `feat(a2): add fail-closed multimodal provider gateway`.
- Push: verified to `origin/dev/g3-a2-calibration`; final remote SHA is recorded by the post-amend remote verification command.

## Exactly 20 next-round implementation tasks

1. Add a normalized provider request JSON Schema.
2. Add a normalized provider response JSON Schema.
3. Add a model registry record with provider, model, version, modality, and lifecycle fields.
4. Add registry capability filtering tests for tenant and modality combinations.
5. Add Ollama `/api/tags` model discovery with normalized records.
6. Add an Ollama health probe with explicit timeout status.
7. Add an opt-in local Ollama text smoke command that emits public-safe evidence.
8. Add an opt-in local Ollama image smoke command using content hashes only in persisted evidence.
9. Add one OpenAI-compatible adapter shared by compatible cloud endpoints.
10. Add a credential resolver protocol that returns secrets only at the adapter boundary.
11. Add tenant provider/model allowlist policy enforcement.
12. Add data-residency policy enforcement before invocation.
13. Add request byte/count limits per modality.
14. Add deterministic pre-call budget estimation and reservation interface.
15. Add bounded retry policy limited to explicitly retryable failures.
16. Add timeout and circuit-breaker state contracts.
17. Add per-attempt token/cost ledger records without raw payloads.
18. Add semantic judge structured-output JSON Schema validation.
19. Add an A3-facing public provider provenance handoff builder and tests.
20. Add an authenticated A1 evidence-bundle verification gate before provider authorization.
