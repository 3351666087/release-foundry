# releasefoundry-runtime-verify

Production-oriented Rust verification sidecar for self-host runtime smoke checks,
public-safe evidence bundles, and authenticated identity-verification envelopes.

Commands:

- `releasefoundry-runtime-verify verify <path>` checks that a local ReleaseFoundry fixture/state JSON has balanced braces, a recognized runtime marker, and no obvious secret tokens.
- `releasefoundry-runtime-verify replay-plan <path>` emits a deterministic JSON plan that identifies queued/running runs by scanning the local state text.
- `releasefoundry-runtime-verify verify-bundle <path>` performs the legacy
  integrity-only check for `releasefoundry.a1.evidence_bundle.v1`. Because its digest is
  stored in the same unsigned document, it detects accidental corruption but
  does not authenticate the producer.
- `releasefoundry-runtime-verify verify-signed-bundle <path> --key-env <NAME> [--now-ms <MILLISECONDS>]`
  verifies a strict `releasefoundry.a1.authenticated_evidence_bundle.v2` manifest. Its
  HMAC authenticates bundle identity, tenant/project scope, validity window,
  and the canonical evidence digest. Optional
  `--expected-tenant-digest <SHA256>` and
  `--expected-project-digest <SHA256>` bind the invocation to trusted scope.
  Its result explicitly reports `verification_level=manifest_authenticated`
  and does not claim that artifact bytes were opened.
- `releasefoundry-runtime-verify verify-signed-bundle-objects <path> --key-env <NAME> --object-root <PATH>`
  authenticates the manifest and then streams every declared local object.
  Its result explicitly reports `verification_level=objects_verified`.
  `--max-object-bytes <BYTES>` and
  `--max-total-bytes <BYTES>` can lower the default 1 GiB per-object and 4 GiB
  aggregate limits.
- `releasefoundry-runtime-verify canonicalize <path>` emits recursively key-sorted,
  whitespace-free canonical JSON and rejects duplicate object keys and
  floating-point values.
- `releasefoundry-runtime-verify verify-envelope <path> --key-env <NAME> [--now-ms <MILLISECONDS>]`
  verifies a strict digest-only
  `releasefoundry.identity_verification.authenticated_envelope.v1` document. The HMAC key
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
signature mismatches. Environment key strings are wrapped in zeroizing storage
for their verifier lifetime. Artifact paths are confined relative POSIX paths with a
portable ASCII component allowlist, preventing traversal, NTFS alternate data
streams, and cross-platform normalization aliases. Key material remains
environment-only and is never accepted as an argument or emitted.

Object verification is available only from a `VerifiedEvidenceBundle`. Before
opening any object it rebinds the current manifest to the authenticated
canonical bytes, rejects duplicate paths, checks each declared size, checks the
overflow-safe aggregate size, and applies both limits. Each reader is capped at
the declared length, hashed incrementally with a 64 KiB buffer, and then probed
for exactly one extra byte. Short reads, I/O failures, oversized streams, and
SHA-256 mismatches are distinct failures. Zero-byte objects still require EOF
and the SHA-256 of empty content.

The local adapter canonicalizes and anchors the configured root, accepts only
regular files, and rejects symlink/reparse points at every artifact path
component. On Unix, every component is opened with `openat` relative to the
already-open parent directory and with `O_NOFOLLOW`; the final object also uses
`O_NONBLOCK`, so a FIFO or device node cannot stall before its type is rejected.
This descriptor-relative walk remains confined to the held root even if a path
is concurrently renamed. The adapter compares stable file identity and repeats
root, path, identity, and metadata checks around streaming. Unsupported
platforms fail closed when a stable file identity is unavailable. It does not
extract archives or write to the object root.

Windows retains an honest residual TOCTOU boundary because its portable path
walk cannot atomically pin every intermediate component. Holding the root
handle, reparse-point rejection, canonical confinement, handle identity, and
pre/post checks narrow that window and turn observed changes into failures;
they are not a substitute for an object root whose directories are not writable
by untrusted users. The Windows identity check uses the operating system
handle-information API via `windows-sys`; hashing and authentication remain
RustCrypto implementations.

A successful result certifies the bytes read from the opened file handle; it
does not lock the path or promise that another process cannot modify it after
verification returns. Likewise, authenticated tenant/project digests become a
local authorization boundary only when the caller supplies the corresponding
expected digests. Production invocations against a scope-specific root should
set both expected-scope options.
