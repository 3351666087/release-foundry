# M10 Platform And Runtime

Owner lane: A1. A3 may consume contracts and evidence but must not rewrite runtime semantics.

## Checklist

- [x] `M10-01` Local Runner emits RunResult, Observation, Trace and ToolCall evidence.
- [x] `M10-02` Python, TypeScript and Go SDK surfaces have automated contract coverage.
- [x] `M10-03` Hosted API/control-plane contracts, API key scope and usage shapes exist.
- [x] `M10-04` PostgreSQL, queue/worker, object storage and self-host deployment scaffolds exist.
- [ ] `M10-05` Prove live PostgreSQL, object storage and worker persistence in a target environment.
- [ ] `M10-06` Prove tenant-bound identity and authorization on every mutating runtime path.
- [ ] `M10-07` Publish immutable runtime image digests and deployment receipts.

## Evidence To Load

- `docs/a1/README.md`
- `docs/a2/a1_a3_handoff.md`
- `packages/sdk`
- `packages/ts/releasefoundry`
- `packages/go/releasefoundry`
- `services/runner`
- `infra/docker`

## Evidence Log

- `2026-07-20`: main CL Gate passed Python A1/A2, TypeScript SDK, Go SDK/integration and release contracts at `c32d635ecb100a585369188f86f5c184c8645775`.
