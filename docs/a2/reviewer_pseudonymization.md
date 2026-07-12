# A2 reviewer pseudonymization

A2 stores a reviewer receipt only as `sha256:<64 lowercase hex>` plus the signed
review timestamp. The digest must be derived outside A2 from a stable,
tenant-scoped pseudonymous reviewer identifier. Raw names, email addresses,
employee numbers, identity-provider subjects, prompts, comments and free-text
review reasons must not enter the quality proof or recovery envelope.

Recommended derivation:

```text
sha256("a2-reviewer-v1" || tenant-specific random salt || stable reviewer subject)
```

The tenant salt belongs in an external secrets or identity service and must not
be committed with evidence. Different tenants should produce different digests
for the same human. Rotation creates a new digest and must be auditable by the
identity authority. A2 treats the digest as provenance, not proof that the
review was substantively correct; calibration and policy checks remain required.

For rotation, the identity authority should retain a public-safe receipt with
the tenant reference, old salt-version identifier, new salt-version identifier,
rotation timestamp, reason code and authorizing principal digest. It must never
retain either salt in A2. Existing signed reviews keep their original reviewer
digest and salt-version provenance; rotation must not rewrite historical
Decision Ledger records or silently relink identities across salt versions.
