# M70 Release Distribution

## Checklist

- [x] `M70-01` Build independent Product and Customer Agent Release candidates.
- [x] `M70-02` Emit manifests, verification, checksums, SBOM, provenance and release notes.
- [x] `M70-03` Publish both candidates from a clean, fully tested `main` SHA.
- [x] `M70-04` Download every GitHub asset and verify hashes, ZIPs and cross-release binding.
- [ ] `M70-05` Replace mutable service tags with immutable image digests.
- [ ] `M70-06` Add real artifact signatures and signature verification receipts.
- [ ] `M70-07` Attach every live receipt required by Product Release policy.
- [ ] `M70-08` Automate reproducible build and publish in a protected release workflow.

## Evidence To Load

- `docs/releases/github_dual_release_runbook.md`
- `services/release_distribution`
- `services/product_release`
- `services/customer_release`
- latest GitHub Release metadata only

## Evidence Log

- `2026-07-20`: both GitHub Releases exist as explicit `NO-GO` prereleases at main SHA `c32d635ecb100a585369188f86f5c184c8645775`.
