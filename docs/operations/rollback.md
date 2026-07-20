# Rollback

Rollback is permitted only to a release whose schema and evidence formats can read the current data.

## Trigger conditions

- Health or readiness failure after upgrade.
- Tenant isolation, identity, billing, audit, or evidence-integrity regression.
- Unrecoverable queue growth or worker failure.
- Security incident requiring immediate containment.

## Procedure

1. Stop new release mutations and preserve incident evidence.
2. Record the failed Product Release ID and current database migration.
3. Restore the previous immutable image digests and configuration.
4. Reverse only migrations explicitly marked reversible. Otherwise restore the verified backup into an isolated replacement environment.
5. Verify API health, worker persistence, identity, tenancy, audit chain, and object hashes.
6. Reopen traffic gradually and retain both failed and recovery receipts.

Do not erase the failed deployment or rewrite its audit records after rollback.
