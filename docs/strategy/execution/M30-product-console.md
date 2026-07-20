# M30 Product Console

Owner lane: A3. The UI projects A1 execution evidence and A2 evaluation authority.

## Checklist

- [x] `M30-01` Next.js route-level Product Console replaces the monolithic HTML path.
- [x] `M30-02` Runs, Cases, Trace, Expected vs Actual, Failure Cluster and Reports are present.
- [x] `M30-03` Review, GitHub gate, deployment receipt, admin, billing and trust surfaces exist.
- [x] `M30-04` Chinese/English, desktop/mobile and bounded-density layouts have E2E coverage.
- [x] `M30-05` API Reference and fail-closed authentication states are represented.
- [ ] `M30-06` Replace remaining fixture-backed projections with tenant-scoped hosted APIs.
- [ ] `M30-07` Bind UI authorization to trusted server identity instead of client-supplied role hints.
- [ ] `M30-08` Prove hosted report share, expiry, revocation and audit in a deployed environment.

## Evidence To Load

- `apps/webapp`
- `services/report`
- `tests/e2e/a3-webapp-product-routes.spec.ts`
- `docs/a3/a3_integration_plan.md`
- current A1/A2 handoff files only

## Evidence Log

- `2026-07-20`: main CL Gate passed A3 Node and Next.js/Playwright jobs at `c32d635ecb100a585369188f86f5c184c8645775`.
