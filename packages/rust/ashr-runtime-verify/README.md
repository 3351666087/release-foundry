# ashr-runtime-verify

Small dependency-free Rust utility for self-host runtime smoke checks.

Commands:

- `ashr-runtime-verify verify <path>` checks that a local Ashr fixture/state JSON has balanced braces, a recognized runtime marker, and no obvious secret tokens.
- `ashr-runtime-verify replay-plan <path>` emits a deterministic JSON plan that identifies queued/running runs by scanning the local state text.

The utility intentionally avoids external crates so it can be compiled in locked-down self-host environments after Rust is installed.
