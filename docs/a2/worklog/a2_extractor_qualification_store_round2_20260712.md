# A2 Extractor Qualification Store — 2026-07-12

## Mainline and synchronization boundary

- This task remains the sole A2 writer on `dev/g3-a2-calibration`; the prior task is paused and no concurrent ownership is assumed.
- `git fetch origin --prune` was attempted before implementation but GitHub port 443 was unreachable. Consequently, branch review used the last locally cached refs only: `origin/main=ccf6ce5`, `origin/agent/a3-commercial-growth-round4=ccf6ce5`, and `origin/agent/a1-local-sdk-runner=b6033ab`.
- The cached `HEAD..origin/main -- docs/strategy` comparison has no delta. This is not represented as a live-network freshness guarantee.
- Scope is limited to A2-owned qualification persistence, schema, tests, and this worklog.

## Delivered contract

- SQLite persistence for immutable extractor qualification records.
- Durable revocations with generation-based stale-writer fencing.
- Restart reconstruction of the qualification registry.
- Public-safe snapshot metadata containing schema version, generation, counts, and a deterministic snapshot hash, but no raw records or secret material.
- Trusted issuer configuration schema with explicit generation and activation time.
- Immutable extractor/version identity rejects both changed content and alternate record IDs.
- Reload independently checks database identity and content hashes, so direct payload tampering fails closed.
- Issuer rotation causes records from removed authorities to fail closed during reconstruction.

These checks are deterministic offline contract checks. They do not constitute live production database qualification, external signature verification, key custody, or Provider validation.

## Microscopic simulations

### Round 1 — restart and revocation race

Writer A persists a valid qualification at generation 0, producing generation 1. A stale writer attempts revocation with generation 0 and is rejected. The current writer revokes at generation 1, producing generation 2. Reconstructing from a fresh registry view retains the revocation and blocks deployment qualification.

### Round 2 — storage and identity tamper

An attacker modifies serialized extractor content directly in SQLite while leaving the stored hash unchanged; reload rejects the row before registry use. A second attacker submits the same extractor/version under a different record ID with an internally consistent new hash; immutable identity conflict rejects it instead of returning a misleading summary.

## Macroscopic A1/A2/A3 simulations

### Round 1 — normal evidence path

A1 supplies scoped evidence and provenance. A2 reconstructs only qualifications accepted under the current trusted-issuer set, validates deployment bindings, evaluates policy, and remains the sole release-decision authority. A3 consumes A2's public-safe status and decision without reading raw qualification records or recomputing the decision.

### Round 2 — issuer rotation and compromised extractor

A trust rotation removes the old qualification authority. On reload, A2 fails closed for records issued only by that authority. A durable emergency revocation similarly survives process restart. A1 cannot override either trust outcome, and A3 cannot reinterpret or bypass the blocked A2 result.

## Growth auditor

Actual completion in this round covers durable persistence, durable fenced revocation, snapshot provenance, trusted-issuer schema/rotation behavior, and two narrow fail-closed storage tests. The earlier queue is not claimed as fully complete. Commit and push status must be recorded from actual command results only.

## Next growth queue (exactly 20)

1. Implement a trusted-issuer config loader that validates schema before use.
2. Enforce trusted-issuer `valid_from` activation time.
3. Bind snapshot provenance to the trusted-issuer config digest.
4. Add an external attestation verifier interface without claiming signatures.
5. Defer signed-attestation support until real key custody and rotation exist.
6. Bind qualifications to extractor configuration digests.
7. Bind qualifications to dictionary digests where applicable.
8. Bind qualifications to dependency-lock digests.
9. Add normalized OS and CPU architecture compatibility tests.
10. Add explicit BCP-47 language fallback policy tests.
11. Add media subtype and parameter normalization tests.
12. Define qualification renewal overlap and rollback behavior.
13. Propagate emergency suspension to in-flight evaluations.
14. Add cache freshness and stale-read fail-closed tests.
15. Add tenant policy constraints without allowing tenant-issued trust.
16. Ingest synthetic parser-sandbox evidence with an explicit offline label.
17. Ingest synthetic malware-engine evidence with an explicit offline label.
18. Add public-safe qualification status to the A3 report contract.
19. Add golden regressions for credential-transfer and row-tamper attacks.
20. Add one unified local CLI for project-scoped evaluation inputs.
