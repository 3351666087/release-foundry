# ashr-runtime-verify

Small Rust utility for self-host runtime smoke checks and public-safe A1 evidence bundle verification.

Commands:

- `ashr-runtime-verify verify <path>` checks that a local Ashr fixture/state JSON has balanced braces, a recognized runtime marker, and no obvious secret tokens.
- `ashr-runtime-verify replay-plan <path>` emits a deterministic JSON plan that identifies queued/running runs by scanning the local state text.
- `ashr-runtime-verify verify-bundle <path>` verifies a public A1 evidence bundle shaped as `ashr.a1.evidence_bundle.v1`, rejects secret-like markers, recomputes SHA-256 over the bundle `evidence` value, and fails closed when `evidence_sha256` does not match.

The runtime commands keep their string-scanning behavior for locked-down self-host fixtures. The bundle verifier uses `serde_json` and `sha2` so tampering checks run against parsed JSON instead of ad hoc text.
