# Upgrade

1. Read both the Product Release verification and release notes.
2. Block the upgrade if the target release is `NO-GO`, lacks immutable image digests, or has no compatible rollback path.
3. Back up PostgreSQL and object-store evidence.
4. Verify current tenant isolation and audit health before changing anything.
5. Pull assets by digest, not mutable tags.
6. Validate configuration and run migration preflight.
7. Upgrade a staging or canary environment first.
8. Run identity, billing, SDK, multimodal, report, and A1/A2/A3 integration smoke tests.
9. Promote only after health, migration, persistence, and audit receipts pass.

Record the old and new Product Release IDs, manifest hashes, image digests, migration IDs, operator identity, timestamps, and all verification outputs.
