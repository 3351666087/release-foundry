# A2 Isolated Extractor Runtime - Round 2

Date: 2026-07-12

## Strategy alignment

This slice follows `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.
It makes untrusted artifact parsing a fail-closed execution boundary before
adding OCR, ASR, document parsers or video tooling.

A2 remains the authority for evidence eligibility. A successful upload,
authorization or parser process exit is not a Release Decision.

## Implemented

- A JSON-over-stdio extractor worker protocol.
- A real Python subprocess execution path for PNG, JPEG, WAV, PDF, MP4 and
  supported text structures.
- Wall-clock timeout enforcement.
- Explicit worker exit, protocol and input-binding failure classes.
- Input hash and media-type response binding.
- Runtime, protocol, configuration hash, latency and exit-code provenance.
- Production policy that can require isolated extraction.
- Fail-closed behavior when isolation is required but unavailable.
- Policy propagation through the authorized ArtifactReference path.
- Public-safe results that exclude bytes, stderr, commands and local paths.

## Contract-supported

- Replacing the Python worker with OCR, ASR, PDF and video extractor adapters.
- Adding OS/container CPU, memory, file and network restrictions.
- Persisting extraction jobs and attempts behind a durable worker queue.

## Not production-verified

- OS-level memory and CPU quotas.
- Container, seccomp or Windows Job Object sandboxing.
- Production malware scanning.
- OCR, ASR, PDF text extraction and video keyframes.
- Multi-node extraction workers and production load.

Torch is not installed and is not required by this slice. Model dependencies
will be selected only after their quality, license, hardware, rollback and
offline deployment profiles are defined.

## Two-stage simulation

Micro simulation:

- a normal isolated worker completes;
- a missing required runtime blocks evaluation;
- a timed-out worker fails without creating a Pass;
- the worker response must match the requested hash and media type.

Macro simulation:

- an authorized, immutable ArtifactReference is verified;
- the resolved bytes enter the isolated worker;
- extraction provenance returns to the artifact pipeline;
- only a complete pipeline can enter Evidence Snapshot;
- extraction failure therefore cannot become an A2 allow Decision.

## Independent Growth-Auditor verdict

The trusted authorization and decision control plane is implemented, while
multimodal semantic understanding remains incomplete. The highest-value next
vertical is screenshot OCR with coordinates and citations carried through
Evidence Snapshot, Provider, grounding Judge, Review, Decision and Regression.

## Next growth queue

1. Define `a2.derived_evidence.v1`.
2. Define region, page and timeline citation contracts.
3. Add a versioned extractor registry.
4. Record extractor license and artifact digest.
5. Add subprocess output-size limits.
6. Add OS-level CPU and memory limits.
7. Disable worker network access by policy.
8. Add durable extraction job and attempt storage.
9. Add lease, fencing, retry and dead-letter semantics.
10. Add production malware and quarantine adapters.
11. Add real PNG/JPEG decode and normalization.
12. Remove EXIF and GPS metadata.
13. Add a replaceable OCR adapter contract.
14. Benchmark a CPU OCR reference backend.
15. Emit OCR text, boxes and confidence.
16. Detect visual prompt injection as untrusted evidence.
17. Bind derived evidence into Evidence Snapshot.
18. Pass public-safe derived text and citations to Providers.
19. Reject empty or placeholder multimodal Provider payloads.
20. Add citation-grounding Judge semantics.
21. Route low-confidence extraction to human Review.
22. Promote reviewed corrections to governed regression candidates.
23. Add old-versus-new extractor shadow comparison.
24. Add extraction latency, failure and quality telemetry.
25. Implement an A1 ArtifactReference v2 issuer.
26. Add a version-pinned MinIO/S3 reader.
27. Add a real A1-to-A2-to-A3 multimodal test.
28. Add parser and model SBOM generation.
29. Add PDF native text plus rendered-page OCR.
30. Add timestamped ASR.
31. Add video keyframes, audio tracks and timeline citations.
32. Prove the complete path under a customer VPC/offline profile.
