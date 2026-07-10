# ashr-runtime-verify

Production-oriented Rust verification sidecar for self-host runtime smoke checks,
public-safe evidence bundles, and authenticated identity-verification envelopes.

Commands:

- `ashr-runtime-verify verify <path>` checks that a local Ashr fixture/state JSON has balanced braces, a recognized runtime marker, and no obvious secret tokens.
- `ashr-runtime-verify replay-plan <path>` emits a deterministic JSON plan that identifies queued/running runs by scanning the local state text.
- `ashr-runtime-verify verify-bundle <path>` performs the legacy
  integrity-only check for `ashr.a1.evidence_bundle.v1`. Because its digest is
  stored in the same unsigned document, it detects accidental corruption but
  does not authenticate the producer.
- `ashr-runtime-verify verify-signed-bundle <path> --key-env <NAME> [--now-ms <MILLISECONDS>]`
  verifies a strict `ashr.a1.authenticated_evidence_bundle.v2` manifest. Its
  HMAC authenticates bundle identity, tenant/project scope, validity window,
  and the canonical evidence digest. Artifact paths must be confined relative
  POSIX paths, closing absolute-path and traversal ambiguity before a caller
  maps entries into a sandbox. Components use a portable ASCII allowlist,
  preventing NTFS alternate-data-stream and cross-platform normalization
  aliases.
- `ashr-runtime-verify canonicalize <path>` emits recursively key-sorted,
  whitespace-free canonical JSON and rejects duplicate object keys and
  floating-point values.
- `ashr-runtime-verify verify-envelope <path> --key-env <NAME> [--now-ms <MILLISECONDS>]`
  verifies a strict digest-only
  `ashr.identity_verification.authenticated_envelope.v1` document. The HMAC key
  is read from a named environment variable and is never accepted as a command
  argument or emitted in output.

The runtime commands keep their string-scanning behavior for locked-down self-host fixtures. The bundle verifier uses `serde_json` and `sha2` so tampering checks run against parsed JSON instead of ad hoc text.

## Authenticated envelope boundary

The library API provides:

- strict `deny_unknown_fields` deserialization and duplicate-key rejection;
- recursively sorted canonical JSON with integer-only numbers;
- HMAC-SHA256 authentication and constant-time key-id, scope, and signature
  checks;
- explicit replay/idempotency guard inputs for a durable external store;
- distinct `Fresh`, `IdempotentReplay`, `Conflict`, and `ReplayedNonce`
  outcomes;
- digest-only tenant, project, principal, event, request, nonce, payload, and
  evidence fields;
- expiration, maximum-lifetime, and expected-scope policy checks.

The verifier does not implement an in-process production replay database.
Production callers must inject a durable `ReplayGuard` and atomically reserve
the event/idempotency/nonce tuple in their database transaction.

The cross-language vector at
`test-vectors/identity_verification_hmac_sha256_v1.json` fixes the canonical
signing bytes and HMAC output so Go, Python, TypeScript, and Rust can consume
the same contract.

## Authenticated evidence bundle boundary

The v2 bundle verifier rejects unknown and duplicate fields, empty or oversized
manifests, unsafe artifact paths, malformed artifact digests/media types,
expired or overlong attestations, evidence digest mismatches, unknown keys, and
signature mismatches. Key material remains environment-only.

The verifier authenticates a manifest; it deliberately does not open or extract
archive contents. A storage service must separately compare each declared
artifact size and SHA-256 while streaming bytes into a confined destination.
The implementation is pure Rust and RustCrypto. GCC/FFI would enlarge the
memory-safety and build surface without improving this HMAC/canonical-JSON
boundary, so this slice does not link native C code.
