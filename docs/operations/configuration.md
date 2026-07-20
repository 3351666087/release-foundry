# Configuration

Ashr configuration separates public settings from credentials. Commit only examples and variable names; values belong in an enterprise secret manager or a protected local environment file.

## Required baseline

- PostgreSQL authentication secret and DSN reference.
- Redis URL reference.
- Object-store endpoint, bucket, access-key reference, and secret-key reference.
- Hosted identity and OAuth provider references when those features are enabled.
- Payment-provider references only for enabled providers.
- Explicit organization, tenant, workspace, project, and environment scope.

## Rules

1. Do not place tokens, private keys, cookies, signed URLs, or passwords in Git, manifests, logs, screenshots, or receipts.
2. Keep Provider selection explicit; a failed Provider must never fall back to an unapproved model.
3. Keep China payment networking disabled until the merchant contract and reconciliation path are verified.
4. Validate Compose with `config --quiet` so resolved secrets are not printed.
5. Record only environment variable names and presence state during audits.

Configuration changes that affect identity, tenancy, billing, evidence retention, or release authority require a new Product Release receipt set.
