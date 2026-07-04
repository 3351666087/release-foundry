# P3 Media Evidence Calibration

## Decision

This round selected `Media Evidence` as the highest ROI A3 enhancement.

| Candidate | Workflow value | Demo value | Field fidelity | Risk reduction | Effort | Decision |
|---|---:|---:|---:|---:|---:|---|
| Product console shell | 5 | 4 | 3 | 3 | 3 | Keep improving around selected media work |
| Trace tree + tool-call diff | 4 | 4 | 3 | 3 | 4 | Backlog |
| Media evidence | 5 | 5 | 5 | 4 | 3 | Selected |
| Report center | 3 | 4 | 2 | 2 | 3 | Backlog |
| Official Ashr dashboard/API calibration | 4 | 4 | 5 | 5 | 4 | Continue as evidence work |

Media evidence won because the P3 API sample already showed real `audio`, `file`, `action_tags`, `output_path`, and `vm_stream` fields, while the previous A3 mapper and dashboard only handled text/tool-call cases well.

## Real Ashr Evidence

Read-only Ashr SDK calibration produced sanitized samples under `fixtures/a3/p3`.

Observed media-related fields:

- `dataset_source.dataset_type`
- `dataset_source.runs.*.actions[]`
- `actions[].action_type`: `text`, `file`, `audio`
- `actions[].action_tags.file`
- `actions[].output_path`
- `actions[].expected_response.tool_calls`
- `run.result.cases[]`
- `cases[].metadata.action_type`
- `cases[].metadata.audio_tags`
- `cases[].metadata.intent_tags`
- `cases[].metadata.action_tags`
- `cases[].observations[].vm_stream`
- `grade.expected`
- `grade.actual`
- `grade.metrics`
- `grade.passed`
- `grade.score`

Sanitized evidence files:

- `fixtures/a3/p3/ashr_media_field_sample.redacted.json`
- `fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`

## Mapper Result

`services/report/p3_ashr_mapper.mjs` now supports two real Ashr run shapes:

- `run.result.tests[].action_results[]`
- `run.result.cases[]`

The mapper now emits `case.media_evidence` when media fields are present:

- `primary_media_type`
- `media_types`
- `evidence_items`
- `action_tags`
- `output_paths`
- `audio_tags`
- `intent_tags`
- `vm_streams`
- `known_gaps`

It also emits media timeline events such as `media.vm_stream`, so the Trace Timeline can show replay-like evidence even when observability traces are not enabled on the account.

## Dashboard Result

`apps/dashboard/index.html` now has:

- A product-console title and navigation.
- Data source switcher:
  - `A1/A2 Mock`
  - `P3 Media Sample`
- Overview metrics with `Media Evidence`.
- Workflow panel: requests, datasets, runs, analysis, export.
- Usage / Quota panel with known-gap wording.
- Objects panel for requests/datasets/runs summary.
- Case Detail `Media Evidence` panel.
- Empty/known-gap media state for mock cases.
- P3 media view backed by redacted local sample plus mapper.

## Known Gaps

- The sanitized media sample does not include a direct downloadable signed media URL for audio cases.
- `usage` and `quota` are not available as first-class A3 fixture fields yet.
- The Ashr lab UI required sign-in, so official authenticated dashboard layout still needs manual observation.
- Native Ashr failure class is still not confirmed; A3 derives failure class from grade metrics for the `result.cases[]` sample.

## Verification

- `node --test tests/a3/report_builder.test.mjs`
- `node --test tests/a3/p3_ashr_mapper.test.mjs`
- Browser smoke test at `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`
- Desktop and mobile screenshots saved:
  - `docs/screenshots/a3-p3-product-console-media-overview.png`
  - `docs/screenshots/a3-p3-product-console-media-mobile.png`

## Next Top 3

1. Add a trace/tool-call diff panel that compares expected vs actual tool calls side by side.
2. Add a report-center view that makes exports feel like a product workflow, not only buttons.
3. After manual login, observe the authenticated Ashr lab dashboard and update the A3 navigation model.
