# A2 Real API C3 Discovery

Date: 2026-07-05
Branch: `dev/g3-a2-calibration`

Purpose: use the authorized Ashr API key through the current process environment only, then decide whether A2 can safely fill the C3 `ashr_grading` column.

Private/raw outputs stayed under ignored `docs/evidence/private_refs/`. No API key, email address, authorization token, raw prompts, or raw response payload is committed here.

## Read-Only Calls

- `list-runs --limit 100`: reached the API, returned 2 runs.
- `get-run 11924`: reached the API, returned 0 visible tests and 0 A2 C3 matches.
- `get-run 11923`: reached the API, returned 1 visible test and 0 A2 C3 matches.
- `list-datasets --limit 100`: reached the API, returned 3 datasets.
- `get-dataset 881`, `882`, `883`: reached the API; details showed dataset metadata and `dataset_source.total_runs`, but no A2 C3 test IDs.
- `list-runs --dataset-id 881`, `882`, `883`: reached the API; returned run `11923`, run `11924`, and no run respectively, still with 0 A2 C3 matches.
- `list-requests --limit 100` plus `get-request 577`, `579`, `580`, `581`, `582`: reached the API; some requests were completed and some failed, but none contained the six A2 C3 test IDs.

## Result

C3 is not safe to mark met yet. The account currently has live API reachability, but no discovered Ashr run contains the required mapped test IDs:

- `ashr-a2-g3-s001-pass`
- `ashr-a2-g3-s010-wrong-arguments`
- `ashr-a2-g3-s031-media-unsupported-output`
- `ashr-a2-g3-s041-poor-retry-recovery`
- `ashr-a2-g3-s048-secret-leak`
- `ashr-a2-g3-s054-missing-clarification`

I did not execute a mutating `create-run` from these findings. The visible datasets/runs do not establish that an uploaded local result would produce comparable server-side grading for the six A2 calibration cases.

## Next Safe Step

Use `scripts/a2_scan_ashr_grading_evidence.py` on any future private `get-run`/`list-runs` evidence before import. Import into the public calibration matrix only when the scan reports all six expected cases and the private evidence has been human reviewed.
