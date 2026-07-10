# A2 A1 Object Storage Context - 2026-07-10

## Scope

- Lane: A2 Evaluation / Policy / Security.
- Service boundary: `services/judge/evidence_readiness.py`.
- Contract: `docs/a2/schemas/evidence_readiness.schema.json`.
- Generated artifact: `fixtures/a2/results/a2_evidence_readiness_report.json`.

## Upstream Signal

- `origin/main` is integrated through `5dbf4ee Merge pull request #30 from 3351666087/codex/main-sync-a1-a2-a3-readme-20260710`.
- `origin/main` now includes A1 object storage contract evidence at `docs/a1/evidence/object_storage_contract_20260709.md`.
- The strategy bus still requires A2 to strengthen public-safe evidence handoff, artifact/bundle semantics, redaction correctness, and A1/A3 consumption compatibility.

## A2 Behavior

- A2 now optionally consumes the A1 object storage contract evidence note when present.
- The summary records schema version, supported backends, scoped object-key policy, public manifest fields, manifest signature, checksum readback, local readback, S3-compatible reference-only boundary, lazy network adapter boundary, SDK/API wiring, evidence bundle metadata wiring, public redaction flags, and test targets.
- The context is ready only when public manifests are hash/reference based, checksum/readback semantics are present, storage network reads are explicit, object metadata can flow into evidence bundles, and public records do not include raw payload bytes, local absolute paths, raw endpoints, key values, or token material.
- `c3_grading_ready` remains false; object storage evidence is artifact/bundle policy context, not reviewed Ashr grading evidence.

## Verification Plan

- `python -B scripts/a2_regenerate_fixtures.py --check`
- `python -B -m unittest discover -s tests/a2 -v`
- A3 compatibility test if A2 public artifact consumption changes require it.
- `git diff --check`
- staged secret scan before commit.

## Notes

- No live Ashr API call was needed for this change.
- No private evidence path was read or committed.
