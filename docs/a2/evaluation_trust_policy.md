# A2 evaluation trust policy

`a2.evaluation_trust_policy.v1` is a public-safe, content-addressed policy used
to verify evaluation quality proofs. Its normalized hash is bound into the
request identity, recovery envelope, Decision Ledger policy hash and public
bundle-evaluation reproducibility output.

## Empty issuer allowlist

An empty `allowed_issuers` array means that issuer allowlisting is disabled.
Signature, key, lifetime, binding, revocation and review-receipt checks still
apply. This compatibility mode is explicit and test-covered; it does not mean
that proofs are trusted without cryptographic verification.

`issuer_tenants` must be empty in that mode. A tenant mapping is accepted only
for an issuer named in `allowed_issuers`. Production deployments should use a
non-empty issuer allowlist and explicit tenant mappings.

## Public identifiers

Revoked key identifiers are public provenance, not credentials. They are
limited to 1–128 ASCII characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, `:`,
`/`, and `-`, and must start with an alphanumeric character. Revoked proof
references must be canonical lowercase `sha256:` hashes.

Arrays and tenant lists are deduplicated and sorted before hashing, so equivalent
policy documents produce the same policy hash.
