# A2 Multimodal Artifact Pipeline - Round 1

Date: 2026-07-12

## Strategic alignment

This round implements the first Provider-independent data-plane slice required by
`docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

A2 remains the authority for evidence eligibility and Release Decision. A1 may
supply artifact references and bytes through a governed storage boundary. A3 may
display extraction state and the effective A2 Decision, but must not infer
release readiness from upload success or recompute A2 eligibility.

## Capability level

### Implemented

- Five-field tenant-scoped artifact submissions.
- SHA-256 content verification.
- Byte-signature media detection for PNG, JPEG, WAV, PDF, MP4 and UTF-8 text.
- Claimed MIME versus detected MIME validation.
- Artifact byte, image pixel, audio duration, PDF page and text size policy limits.
- Pluggable malware scanner contract.
- A deterministic development signature scanner with explicit
  `production_qualified=false`.
- Fail-closed behavior when scanning is unavailable, rejected or not production
  qualified under production policy.
- Bounded metadata extraction for supported formats.
- Extraction quality signals and explicit limitations.
- Public-safe output containing hashes and metadata, never raw artifact bytes or
  private source references.
- Binding of accepted artifact and extractor provenance into Evidence Snapshot.
- Versioned `ArtifactReference v1` and public-safe resolution contracts.
- Provider allowlisting, purpose/expiry checks and authorization binding hashes.
- Rejection of naked URLs, mutable version labels and incomplete expected scope.
- Bounded, version-pinned object reader interface with readback verification of
  returned version, size, SHA-256 and media type.
- Resolution integrity and five-field scope verification at the Trusted Spine
  boundary before Evidence Snapshot consumption.
- Evidence Snapshot invalidation on extraction, integrity, scope or scanner
  blockers.
- Existing Decision Ledger prohibition against `allow` when the Evidence
  Snapshot is invalid.

### Contract-supported

- Production malware scanner adapters.
- An A1 issuer/adapter that converts authorized A1 storage records into
  `ArtifactReference v1`.
- Production S3-compatible, Azure Blob and GCS version-pinned reader adapters.
- Provider and model evaluation after artifact extraction.
- A3 display of extraction provenance through the existing Evidence and
  Decision contracts.

### Not production-verified

- OCR and image-region citations.
- ASR and timestamp citations.
- PDF text extraction or rendered-page OCR.
- Video duration, audio track and keyframe extraction.
- Office and archive parsing.
- Parser sandboxing and quarantine infrastructure.
- Production malware engine integration.
- Real customer object-storage retrieval, durable extraction workers and
  production load behavior.
- Cryptographic issuer signatures, key rotation, nonce consumption and
  authorization revocation.
- Conditional network reads and real MinIO/S3 TOCTOU verification.

The current image, audio, file and video implementation is a validated artifact
integrity and structural metadata layer. It must not be marketed as production
OCR, ASR or video understanding.

## Failure semantics

Artifact failures are Evidence failures, not Agent failures. They block
evaluation eligibility and therefore cannot create an A2 `allow` Decision.

The public failure set includes:

- incomplete tenant scope;
- unsafe filename;
- empty or oversized artifact;
- content hash mismatch;
- unsupported or mismatched media type;
- unavailable, failed or blocking malware scanner;
- production scanner requirement not met;
- extractor rejection or unavailable extractor;
- pipeline record integrity or scope mismatch.
- unsupported provider, wrong purpose, expired authorization or mutable version;
- returned object version, size, hash or media-type mismatch;
- tampered ArtifactReference authorization binding or resolution hash.

## Verification evidence

- Real binary structures were generated and parsed for PNG, WAV, PDF and MP4.
- Negative cases cover MIME spoofing, hash mismatch, incomplete tenant scope,
  path-like filenames, oversize artifacts, missing scanners, development-only
  scanners, truncated media and a malware signature.
- A valid image enters Evidence Snapshot as complete.
- A blocked image produces an invalid Evidence Snapshot.
- An invalid Evidence Snapshot cannot produce an `allow` Decision.
- Cross-tenant, wrong-purpose, expired and mutable references are rejected before
  the object reader is called.
- Object replacement, short reads, media drift and returned-version drift are
  rejected after readback verification.
- All 240 A2 tests and 112 selected A3 consumption tests pass.

## A1 alignment finding

A1 already provides scoped object keys, hashes, sizes, canonical manifest
digests and readback verification. Those are reusable integrity primitives, but
they do not yet prove an immutable version or principal authorization. A2's
reference contract is therefore an evaluation authorization envelope, not a
replacement for A1 storage manifests. The next shared boundary should issue this
envelope from an authenticated A1 control-plane decision without exposing raw
object URIs, signed URLs or credentials to A2 or A3.

## Next growth queue

1. Add an A1 issuer/adapter for the implemented `ArtifactReference v1`.
2. Sign references with HMAC or Ed25519 and support key rotation.
3. Add audience, job identity, nonce and durable consumption/revocation state.
4. Add durable ingestion and extraction job state machines.
5. Add leases, retries, fencing and dead-letter handling for extraction workers.
6. Integrate a production malware scanner and quarantine store.
7. Add parser process isolation with CPU, memory and wall-clock limits.
8. Add archive recursion, file-count and decompression-ratio defenses.
9. Normalize image orientation, color space and metadata removal.
10. Add deterministic OCR with bounding-box citations and confidence.
11. Add image prompt-injection labels without treating embedded text as instructions.
12. Add PDF text layers, page rendering, encrypted-PDF policy and OCR fallback.
13. Add Office document parsing with macros and external links disabled.
14. Add audio normalization, segmentation, language detection and ASR timestamps.
15. Add video duration, audio extraction, keyframes and timeline citations.
16. Extend extractor provenance with output hash, config hash, latency and resource cost.
17. Separate extractor, Provider, Judge and Agent failure attribution in reports.
18. Add extraction quality thresholds to project Release Policy.
19. Add capability maturity labels for A3: contract, binary-validated and production-observed.
20. Add a real binary multimodal Golden Set with governed licenses and retention.
21. Add old-versus-new extractor shadow comparison and drift reports.
22. Add per-tenant extraction cost, latency, queue and quality telemetry.
23. Add DashScope and other OpenAI-compatible Provider profiles after extraction.
24. Add local/offline OCR and ASR profiles with pinned model licenses and versions.
25. Complete one screenshot case through OCR, Judge, Review, Decision and Regression.
26. Complete one PDF case through extraction, citations and Release Gate.
27. Complete one audio case through ASR, Judge and human arbitration.
28. Complete one video case through keyframes, timeline Judge and replay.
29. Deliver extraction-resolution events through the existing durable outbox.
30. Run production load, malformed corpus and cross-tenant authorization tests.
31. Implement conditional version reads with bounded streaming for MinIO/S3.
32. Record provider request ID, returned version/ETag and custody timestamps.
33. Add replacement, delete-and-recreate, replay and concurrent TOCTOU tests.

## Commercial assessment

This slice makes A2 responsible for proving that evidence is authentic enough to
be judged, instead of accepting arbitrary media claims from an SDK or Provider.
That reduces false releases and creates the foundation for reproducible
multimodal review, audit and regression. Commercial readiness still requires the
production extraction and worker capabilities listed above.
