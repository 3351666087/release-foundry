# Round 52 Rust Identity Security Verifier

Date: 2026-07-11

## Scope

The existing `packages/rust/ashr-runtime-verify` crate was upgraded in place.
No overlapping Rust crate was created, and no A2/A3 file was modified.

## Security boundary

- Existing `verify`, `replay-plan`, and `verify-bundle` commands remain.
- Canonical JSON recursively sorts object keys, removes insignificant
  whitespace, rejects duplicate object keys, and rejects floating-point
  values.
- The authenticated envelope has a closed schema and contains only SHA-256
  digests for tenant, project, principal, event, idempotency key, request,
  nonce, payload, and evidence identifiers.
- HMAC-SHA256 verification uses the RustCrypto `hmac` crate. Signature
  verification and fixed-scope comparisons use constant-time primitives.
- CLI verification reads key material only from a caller-selected environment
  variable. It does not accept key material in arguments or JSON.
- Replay state is not process-local. The library exposes the complete durable
  guard input and requires callers to return one of fresh, idempotent replay,
  conflicting idempotency reuse, or replayed nonce.
- Production callers must atomically reserve replay/idempotency state in their
  durable transaction. The CLI's allow-fresh guard is a stateless inspection
  tool and is not a production replay database.

## Cross-language vector

`test-vectors/identity_verification_hmac_sha256_v1.json` contains:

- a non-secret test-only HMAC key;
- the strict digest-only envelope;
- exact recursively canonical signing JSON;
- SHA-256 of the canonical bytes;
- expected HMAC-SHA256 signature.

The values were independently generated with Node `crypto` and are
independently recomputed by a Python standard-library contract test. Go and
TypeScript can consume the same JSON without depending on Rust serialization.

## Validation

Commands and final results are recorded without environment values:

```text
cargo fmt --all -- --check
passed

cargo clippy --all-targets --all-features -- -D warnings
passed

cargo test --all-targets --all-features
22 passed (6 unit, 10 authenticated-envelope, 6 authenticated-bundle)

python -m pytest -q tests/a1/test_rust_identity_security_verifier.py
5 passed
```

Environment probe:

```text
Ubuntu-24.04-Ashr GCC
gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
```

The WSL distribution did not have `cargo` or `rustc` installed. A routine
user-space rustup installation was attempted, but the toolchain download
stalled before installation completed and the process was terminated. As a
result, GNU/GCC-linked Cargo tests are not claimed by this round. Windows
Rust 1.96.1 completed all required format, lint, and test gates.

## Known boundary

This sidecar authenticates and validates an envelope. It does not replace the
PostgreSQL transaction that consumes a verification receipt, mutates identity,
and reserves replay/idempotency state atomically.

## Bounded hardening follow-up

Review found that `ashr.a1.evidence_bundle.v1` was only a self-contained
integrity checksum: a malicious producer could change both evidence and its
unsigned digest. The highest-value bounded slice adds
`ashr.a1.authenticated_evidence_bundle.v2`.

- HMAC-SHA256 authenticates schema, key id, bundle id, tenant/project scope,
  canonical evidence digest, and validity window.
- Strict deserialization rejects unknown and duplicate fields.
- Evidence is a bounded typed manifest with SHA-256, byte size, and media type.
- Artifact paths must be relative POSIX paths with no empty, dot, parent,
  backslash, absolute, drive-prefix, NTFS alternate-stream, trailing-dot,
  whitespace, Unicode-normalization, or control-character ambiguity.
- Scope, lifetime, digest, key id, and signature comparisons fail closed.
- The legacy command remains explicitly documented as integrity-only.

This is pure Rust/RustCrypto code. GCC interoperability is not relevant to
canonical JSON and HMAC verification; adding C FFI would increase the
memory-safety and supply-chain surface without adding a security property.

Final validation for this bounded follow-up:

```text
cargo fmt --all -- --check
passed

cargo clippy --all-targets --all-features -- -D warnings
passed

cargo test --all-targets --all-features
22 passed

python -m pytest -q tests/a1/test_rust_identity_security_verifier.py
5 passed
```

Adversarial coverage includes synchronized evidence-plus-self-hash rewriting,
manifest digest tampering, tenant mismatch, parent/absolute/drive/backslash
path escape, duplicate extraction targets, duplicate JSON keys, unknown
security fields, and CLI key non-disclosure.
