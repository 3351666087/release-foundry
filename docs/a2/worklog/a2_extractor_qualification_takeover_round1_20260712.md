# A2 Extractor Qualification Takeover — 2026-07-12

## Takeover boundary

- Current task is the sole writer for `dev/g3-a2-calibration`; the previous pinned task is paused.
- Started from `348536438696532e1e3d30ce2422387846cc5d56`, equal to `origin/dev/g3-a2-calibration` at takeover.
- Preserved and completed the previous task's uncommitted extractor qualification registry; no reset or stash was used.
- Latest observed refs: `origin/main=ccf6ce5`, `origin/codex/a3-commercial-growth-round4=ccf6ce5`, `origin/codex/a1-local-sdk-runner=b6033ab`.
- `docs/strategy` has no `HEAD..origin/main` delta. A1's newer identity/browser-session work does not require an A2 contract change in this round.

## Contract repair

The inherited draft incorrectly risked treating a language/runtime kind (for example `python`) as the same identity as an execution engine (`onnxruntime-cpu`). This round made the deployment identity explicit and exact:

- `runtime.id` binds to Derived Evidence `runtime_id`;
- `runtime.version` binds to `runtime_version`;
- `runtime.platform` is now mandatory in Derived Evidence and binds independently;
- `artifact_digest` binds to the actual `model_hash`;
- extractor ID and version also bind exactly.

A producer-supplied mapping cannot impersonate a `QualifiedExtractor`. Unknown issuer, self-attestation, tamper, expiry, revocation, unsupported media/language, quality failure, and any deployment mismatch fail closed. The canonical SHA-256 record hash is documented as deterministic integrity only, never a cryptographic signature. Public projections redact the raw attestation reference and qualification check details.

## Simulations

### Microscopic 1 — legitimate OCR deployment

A registry-issued RapidOCR qualification matches extractor ID/version, ONNX Runtime ID/version/platform, model digest, media type, language, and observed thresholds. Derived Evidence receives a public-safe binding and may become production eligible, subject to all other safety gates.

### Microscopic 2 — transferable credential attack

The same valid qualification is presented with another model digest or platform. Exact deployment binding fails; `ocr_runtime_not_production_qualified` remains a blocker. A plain dict with forged record fields is also rejected.

### Macroscopic 1 — A1 → A2

A1 continues to provide scoped evidence and SDK/identity contracts. A2 validates scope and immutable evidence, then independently qualifies the extractor used to derive semantic evidence. A1 cannot self-declare that runtime production-qualified.

### Macroscopic 2 — A2 → A3

A2 remains the sole release decision authority. A3 consumes only the public-safe qualification binding, provenance, review state, and release result; it neither sees raw attestation references nor recomputes qualification or release decisions.

## Verification

- Focused registry/evidence/artifact/orchestrator suite: 68 passed.
- Full A2 suite: 278 passed.
- Fixture reproducibility: all 56 generated files match committed output.
- Python compile and `git diff --check`: passed.
- Validation is deterministic/offline contract validation. No external Provider or production extractor was invoked, and no live production qualification is claimed.

## Next growth queue (exactly 20)

1. Persist qualification records in a durable A2 store.
2. Persist revocations with fenced update semantics.
3. Add registry snapshot/version provenance to decisions.
4. Add trusted issuer configuration schema and rotation tests.
5. Add external attestation verifier interface without claiming signatures.
6. Add signed-attestation implementation only when real key custody exists.
7. Bind qualification to extractor config digest.
8. Bind qualification to dictionary digest where applicable.
9. Bind qualification to dependency lock digest.
10. Add platform normalization and architecture compatibility tests.
11. Add BCP-47 language fallback policy tests.
12. Add media subtype and parameter normalization tests.
13. Add qualification renewal overlap policy.
14. Add emergency suspension propagation to in-flight decisions.
15. Add registry cache expiry and stale-read fail-closed tests.
16. Add per-tenant policy constraints without tenant-issued trust.
17. Add production parser sandbox evidence ingestion.
18. Add production malware-engine evidence ingestion.
19. Expose public-safe qualification status in A3 reports.
20. Add golden regression cases for credential-transfer attacks.
