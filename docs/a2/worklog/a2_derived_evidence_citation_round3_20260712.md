# A2 Derived Evidence and Citation - Round 3

Date: 2026-07-12

## Strategy alignment

This slice follows `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
A2 remains the authority for evidence eligibility and Release Decision. Artifact
presence, successful upload, successful extraction and Provider completion are
all insufficient by themselves to produce an allow Decision.

ReleaseFoundry remains an optional calibration Provider. The decision path does not
require ReleaseFoundry, Qwen or another external Provider to execute its deterministic
evidence and fail-closed controls.

## Implemented

- Added the public-safe `a2.derived_evidence.v1` contract.
- Added private OCR evidence with text hashes, confidence, polygons and stable
  Citation IDs.
- Bound OCR evidence to five-field tenant scope, artifact ID and content hash.
- Bound extractor model, configuration and dictionary supply-chain hashes.
- Moved production qualification to an independently supplied trusted policy
  record that must exactly match the extractor identity; producer metadata
  cannot self-promote an extractor.
- Separated artifact modalities from semantically observed modalities.
- Prevented an image file without qualified semantic extraction from satisfying
  the image requirement.
- Added explicit development and production eligibility.
- Required prompt-injection assessment and redaction before production use.
- Required explicit disclosure permission before OCR text can reach a Provider.
- Kept OCR plaintext out of Evidence Snapshot, persisted decisions and public
  fixtures.
- Rejected empty text, hash-only pseudo-media and non-text Provider parts
  without actual data.
- Bound the private Provider payload hash into request identity.
- Grounded Provider evidence references against only the evidence actually
  disclosed to that Provider.
- Required image-dependent decisions to cite a disclosed Derived Evidence
  Citation ID; a Snapshot-only citation is insufficient.
- Blocked missing, invented and undisclosed Provider citations.
- Persisted strict Citation validation in the recovery envelope.
- Rejected recovery envelopes whose `grounded`, `invalid` or `not_available`
  state contradicts the semantic output, blockers or reference hashes.
- Kept Provider failure, malformed output and unqualified OCR fail-closed.
- Updated the A3 handoff fixture so artifact presence no longer implies
  semantic completeness.

## Contract-supported

- Replaceable OCR backends with immutable extractor provenance.
- Public Citation display without disclosing extracted text.
- Private Provider disclosure after tenant policy, redaction and residency
  checks.
- Production-qualified scanners and extractors satisfying image semantics.
- Extension of Derived Evidence to page, region and timeline citations.
- A3 consumption of A2-owned evidence completeness and Release Decision.

## Production verification status

The end-to-end image path is implemented and tested:

```text
ArtifactReference
-> scanner and isolated extraction boundary
-> private OCR Derived Evidence
-> public-safe Evidence Snapshot
-> authorized Provider payload
-> grounded Citation validation
-> Release Decision Ledger
-> A3 handoff
```

This is not yet production-qualified. The local D-drive runtime currently has
RapidOCR 3.9.1 and ONNX Runtime 1.23.2. Torch is not installed. No local OCR
runtime, scanner or model has yet completed production quality, security, load,
license, rollback and offline deployment qualification. The production path
therefore blocks when that qualification is absent.

Audio ASR, document semantic extraction and video keyframe/timeline evidence
are not implemented by this slice.

## Verification evidence

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- A3 Node evidence, provenance, dashboard and report consumption tests.
- Focused Derived Evidence, Trusted Spine and Release Orchestrator tests.

Private OCR text and real Provider responses must remain under
`docs/evidence/private_refs/` and must not be committed.

## Micro and macro simulations

Micro:

- Empty, low-confidence, malformed or tampered OCR blocks.
- OCR from an unqualified runtime blocks before Provider invocation.
- OCR text is disclosed only after passed redaction and explicit permission.
- Invented or missing Provider Citation IDs block an allow Decision.
- Public Snapshot and Decision payloads contain hashes and geometry, not OCR
  plaintext.

Macro:

- A1 can issue an authorized immutable ArtifactReference.
- A2 validates, extracts and classifies semantic evidence.
- A2 owns completeness, Provider grounding and Release Decision.
- A3 displays the committed Decision and cannot infer readiness from an upload.
- A Provider outage or missing production extractor cannot create a false pass.

## Residual risk

- The current trusted qualification record is a synthetic contract fixture,
  not a signed registry attestation or production qualification evidence.
- There is no production malware engine, parser sandbox, CPU/memory quota or
  network isolation proof.
- Citation validation is persisted in the recovery envelope but is not yet a
  dedicated public A3 result field.
- There is no real-provider image matrix or customer-VPC deployment evidence.
- There is no human review UI for correcting OCR blocks and promoting approved
  corrections into governed regression candidates.

## Next growth queue

1. Replace the injected trusted qualification record with a versioned, signed
   extractor registry containing license, artifact digests and promotion audit.
2. Add OCR benchmark packs by language, layout, resolution and corruption.
3. Define production qualification thresholds for OCR precision and recall.
4. Add real RapidOCR CPU benchmark evidence on the target workstation.
5. Add a second OCR backend for shadow comparison and rollback.
6. Add image normalization, orientation correction and metadata removal.
7. Add production malware scanner integration and signature provenance.
8. Add Windows Job Object or container CPU and memory enforcement.
9. Disable extractor network access and prove the restricted-network path.
10. Add durable extraction jobs, attempts, leases and dead-letter handling.
11. Add output-size and decompression-ratio limits.
12. Add PDF native-text extraction with rendered-page OCR fallback.
13. Add Office, HTML and Markdown normalized document evidence.
14. Add ASR Derived Evidence with speaker and timestamp citations.
15. Add video keyframe, audio-track and timeline citations.
16. Add archive manifest extraction with nested-file safety policy.
17. Add public Citation validation metadata to the A3 result contract.
18. Add reviewer correction and immutable OCR revision history.
19. Add double approval for production evidence overrides.
20. Add reviewed correction to regression-candidate promotion.
21. Add extractor old-versus-new shadow replay.
22. Add extraction drift, latency, failure and confidence telemetry.
23. Add OpenAI-compatible real-provider contract tests.
24. Add Qwen text and vision Provider adapters through the common gateway.
25. Add vLLM reference deployment and capability discovery.
26. Add customer endpoint TLS, secret-reference and residency enforcement.
27. Add Provider quota, rate-limit and payment failure matrix tests.
28. Add real-provider cost and usage attribution without logging credentials.
29. Add A1-issued ArtifactReference v2 integration tests.
30. Add A3 evidence completeness, Citation and blocked-reason UI tests.
31. Add a complete A1-to-A2-to-A3 multimodal system test.
32. Prove the complete path in an offline or customer-VPC profile.
33. Add signed extractor/model SBOM and offline package manifests.
34. Add model canary, shadow, drain and rollback evidence.
35. Add governed consent and lineage for reviewer-generated learning data.
36. Re-gate every candidate extractor or model before production promotion.

The highest-value parallel tracks are production extractor qualification,
real-provider compatibility, A1 ArtifactReference integration and A3 Citation
consumption. The closest path to a higher-value enterprise contract is a
reproducible incident-to-evidence-to-decision flow that remains operational in
a restricted customer VPC.
