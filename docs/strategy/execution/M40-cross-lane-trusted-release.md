# M40 Cross-lane Trusted Release

This is the current module. Its purpose is to bind A1 execution, A2 authority and A3 delivery to one candidate identity.

## Checklist

- [x] `M40-01` Product Release and Customer Agent Release have independent IDs, assets and GO/NO-GO decisions.
- [x] `M40-02` Customer verifier rejects stale A2 run IDs and stale A3 tested/source SHAs.
- [x] `M40-03` Generate a fresh A1 run bound to the latest candidate ID and latest `main` SHA.
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
- `fixtures/a3/golden-path/rc3`
- `docs/a1/m40_03_rc3_candidate_run_handoff.md`
- `tests/release/test_m40_a1_candidate_run.py`
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
- `2026-07-20`: PR `#42` merged fail-closed candidate-binding tooling into main at `1d292047e991995fdf52f0545ffff410ee19a171`; its CL Gate passed TypeScript SDK parity and Product release contracts.
- `2026-07-20`: A1 run `a3-golden-20260720-003` bound candidate `a3-golden-agent@0.2.0-rc.3`, source commit `1d292047e991995fdf52f0545ffff410ee19a171`, clean tree `5f7152bb0f0e380d433600ec43bd7ddd80dabd66`, and case-set hash `sha256:eadfadb8233ae2d81affec5c62436973a8086119aecee4a2445ba3475fd4109c`.
- `2026-07-20`: the run passed `3/3`, recorded `100%` Trace completeness and four Tool Calls; recomputable A1 bundle hash is `sha256:0b4fb982ccc5a25a54c8c8ea8744285296502bb6be3113d5220af7f3340e3d6b`.
- `2026-07-20`: focused evidence, release, Runner and schema checks passed; ignored dual-release verification checked `12` assets with no integrity issues but remained a dirty-development `NO-GO` and was not published.
- `2026-07-20`: `M40-03` is complete. `M40-04` remains open; no A2 allow, A3 delivery rebuild, human approval or production authority was generated.
