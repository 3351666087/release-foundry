# Backup And Restore

## Backup scope

- PostgreSQL: tenant data, identity, billing, decisions, audit, outbox, and migration state.
- Object store: evidence objects, report exports, and immutable release archives.
- Configuration: non-secret configuration plus a separately governed secret-manager export.
- Redis is treated as rebuildable cache/queue state unless an environment-specific policy says otherwise.

## Backup

1. Record Product Release ID, image digests, schema migration, and backup timestamp.
2. Quiesce release mutations or use a database-consistent snapshot.
3. Create an encrypted PostgreSQL backup.
4. Snapshot versioned object-store buckets and retention policies.
5. Hash the backup inventory and store it outside the workload account.

## Restore drill

1. Restore into an isolated environment with no production network route.
2. Apply only migrations compatible with the recorded Product Release.
3. Verify row counts, tenant isolation, Decision Ledger chains, audit continuity, object hashes, and report access controls.
4. Run A1/A2/A3 smoke tests before declaring the drill complete.

A backup is not accepted until a restore drill has produced a sanitized receipt.
