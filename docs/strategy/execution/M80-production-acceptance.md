# M80 Production Acceptance

## Checklist

- [ ] `M80-01` Deploy the tested Product Release to a real staging/VPC target.
- [ ] `M80-02` Record deployment identity, image/config digest, migrations and health receipts.
- [ ] `M80-03` Prove tenant isolation, network policy, RBAC and secret-manager boundaries.
- [ ] `M80-04` Run load, fault, queue recovery and data persistence tests.
- [ ] `M80-05` Complete backup/restore, upgrade and rollback drills.
- [ ] `M80-06` Prove logs, metrics, traces, SLOs, alerts and incident response.
- [ ] `M80-07` Complete vulnerability, dependency, image and supply-chain security checks.
- [ ] `M80-08` Obtain customer/operator acceptance and auditable human approval.
- [ ] `M80-09` Issue a new Product GO and Customer Agent GO only after every authority passes.

## Evidence To Load

- `docs/operations`
- `docs/releases/ashr_product_release_policy.v1.json`
- deployment receipts for the exact current release only
- latest Product and Customer verification outputs

## Evidence Log

- No real staging/VPC deployment receipt or production upgrade/rollback authorization has been accepted yet.
