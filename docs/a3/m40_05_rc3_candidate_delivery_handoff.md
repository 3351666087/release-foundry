# M40-05 rc.3 A3 Candidate Delivery Handoff

## Scope

This handoff closes the local A3 generation part of `M40-05` for exactly one
candidate:

| Field | Bound value |
| --- | --- |
| Candidate | `a3-golden-agent@0.2.0-rc.3` |
| A1 run | `a3-golden-20260720-003` |
| Evidence version | `0.2.0-rc.3` |
| A1 source commit | `1d292047e991995fdf52f0545ffff410ee19a171` |
| A1 evidence bundle | `sha256:0b4fb982ccc5a25a54c8c8ea8744285296502bb6be3113d5220af7f3340e3d6b` |
| A2 authority commit | `d3529c356e49ce8502c050f0dad44020031ee0dd` |
| A2 Decision Ledger head | `sha256:af84d7e9e3143f4da06341f2e20f3402c8f44ed5efc8221b18c8ef2869747a4e` |
| A2 grades hash | `sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304` |

The A3 implementation commit is recorded in
`fixtures/a3/golden-path/rc3/a3_candidate_delivery_binding.json`. It is kept
separate from the A1 candidate source commit so neither SHA is silently
relabelled.

## What A3 Generated

- `a3_shared_candidate_identity.json` copies the A1 and A2 identity fields and
  fills only A3's consumed Decision Ledger and grades hashes.
- `a3_candidate_delivery_binding.json` binds the candidate, run, version,
  upstream commits, upstream hashes and A3 implementation commit.
- `gate-report.json`, `github-check.json` and `pr-comment.md` project the A2
  block into A3 delivery output.
- `audit-bundle-index.json` hashes A1 input, A2 authority, both shared identity
  records, the A3 delivery binding and generated gate files.
- `audit-archive-manifest.json` signs that local bundle with an ephemeral local
  Ed25519 key. This is local integrity evidence, not KMS, SSO or production
  signing authority.
- `release-artifact-manifest.json`, `deployment-acceptance.json`,
  `golden-path-status.json` and `release-delivery-index.json` package and expose
  the same candidate binding.

## Authoritative Result

The three local A1 cases and three A2 grades pass, but A2's authoritative
Decision Ledger remains `block`. A3 therefore records:

- candidate binding: `exact`
- delivery status: `blocked_by_a2`
- production ready: `false`
- A2 decision recomputed by A3: `false`

An exact identity means all lanes refer to the same candidate. It does not mean
that candidate is approved for release.

## Deliberately Absent Claims

This rc.3 packet does not reuse rc.2 GitHub Check, PR comment, required-check or
Actions artifact readbacks. It does not claim tenant-bound GitHub App identity,
branch-protection enforcement, hosted deployment, immutable hosted storage,
human approval, KMS signing, production upgrade or rollback.

Those absences remain visible as blocked or not-proven Deployment Acceptance
checks. The generated GitHub Check JSON is a payload for this candidate, not a
receipt proving it was published.

## Reproduce And Verify

Generation must use the preserved implementation commit:

```powershell
node scripts/a3_build_m40_rc3_delivery.mjs --implementation-commit <full-a3-implementation-sha> --generated-at <ISO-time> --json
```

Normal verification does not regenerate the random local archive signature:

```powershell
node scripts/a3_build_m40_rc3_delivery.mjs --check --json
node --test tests/a3/a3_trusted_release_authority.test.mjs tests/a3/a3_candidate_delivery_binding.test.mjs
python -B -m pytest tests/release -q -p no:cacheprovider
```

`M40-06` may consume this packet to recompute Customer verification. It may not
turn the preserved A2 block into an allow decision.
