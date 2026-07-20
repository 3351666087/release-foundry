# M50 SaaS Control Plane

## Checklist

- [x] `M50-01` Local identity, tenant, project, RBAC, API key and audit contracts exist.
- [x] `M50-02` PostgreSQL migration and hosted control-plane shapes exist.
- [ ] `M50-03` Deploy a real tenant-scoped PostgreSQL control plane.
- [ ] `M50-04` Connect trusted email, GitHub and Google identity flows to server sessions.
- [ ] `M50-05` Enforce RBAC and tenant isolation through database and service boundaries.
- [ ] `M50-06` Prove durable audit, outbox, retry and recovery under concurrent traffic.
- [ ] `M50-07` Add enterprise SSO/SCIM only after the core identity boundary is proven.

## Evidence To Load

- `services/api`
- identity-related files in `packages/sdk` and `packages/ts/ashr-clone`
- PostgreSQL migrations referenced by A1
- A3 auth/admin routes directly involved in the current item

## Evidence Log

- No production hosted identity or tenant-isolation receipt has been accepted yet.
