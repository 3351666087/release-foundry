# M40 Cross-lane Trusted Release

This is the current module. Its purpose is to bind A1 execution, A2 authority and A3 delivery to one candidate identity.

## Checklist

- [x] `M40-01` Product Release and Customer Agent Release have independent IDs, assets and GO/NO-GO decisions.
- [x] `M40-02` Customer verifier rejects stale A2 run IDs and stale A3 tested/source SHAs.
- [ ] `M40-03` Generate a fresh A1 run bound to the latest candidate ID and latest `main` SHA.
- [ ] `M40-04` Generate A2 Trusted Spine and Decision Ledger for that exact A1 run.
- [ ] `M40-05` Regenerate A3 gate, delivery index, audit bundle and archive for the same run, SHA and version.
- [ ] `M40-06` Recompute Customer verification with no candidate/run/SHA/version mismatch findings.
- [ ] `M40-07` Preserve authoritative NO-GO unless Product, A2, A3 delivery and human approval all independently pass.

## Definition Of Done

The Product and Customer manifests may use separate release IDs, but every Customer evidence reference identifies the same candidate run, source SHA and evidence version. A3 reports A2 authority without rewriting it.

## Evidence To Load

- `docs/releases/two_release_model.md`
- `services/customer_release/contracts.py`
- `services/release_distribution/builder.py`
- `fixtures/a3/golden-path/rc2`
- newest A1 run output and newest A2 handoff only

## Verification

```powershell
python -B -m pytest tests/release -q -p no:cacheprovider
python scripts/build_dual_release_candidates.py --verify-index dist/releases/dual-release-index.json
```

## Evidence Log

- `2026-07-20`: Product `ashr-product@1.0.0-rc.1` and Customer `agent-release:demo/a3-golden-agent@0.2.0-rc.2` were published as separate GitHub prereleases.
- `2026-07-20`: downloaded 12/12 assets; SHA-256, ZIP integrity, verifier recomputation and Customer-to-Product binding passed.
- `2026-07-20`: `M40-03` remains open because the included A1 run and A2 Trusted Spine do not share one run identity.
