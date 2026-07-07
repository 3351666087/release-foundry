# A2 Case Book

This case book is the reviewer-facing companion to `fixtures/a2/results/a2_case_book.json`.

It records calibration disagreements that should remain visible until reviewed Ashr grading or audited live LLM evidence resolves the boundary.

## C5 Maturity Gate

- Calibration cases: `6`
- Local-vs-LLM comparable cases: `6`
- Local-vs-LLM mismatch candidates: `1`
- Promoted regression cases: `1`
- Reviewed external evidence cases: `0`
- Missing Ashr grading observations: `6`
- Mature target: `3` reviewed disagreement regressions
- Current status: `seed`

C5 remains partial because 2 more reviewed disagreement regressions are needed, and the regression set still needs reviewed Ashr grading or audited semantic evidence before the case book and replay suite should be called mature.

## Incident Regression Candidates

Production incidents can enter the case-book review queue through `fixtures/a2/results/a2_incident_regression_candidates.json`.

The current public-safe candidate is `prod-inc-2026-07-support-status-retry`, mapped to `sample-a2-s041-poor-retry-recovery` / `A2-S041`. It is replayable through `fixtures/a2/runs/a2_s041_poor_retry_recovery.json` and preserves local `primary_failure_class=poor_failure_recovery`.

This candidate is not counted as a mature C5 replay case yet. It still needs A2 owner review plus reviewed Ashr grading or audited semantic evidence before it can be promoted from `candidate` into the case-book regression set.

## Regression: sample-a2-s010-wrong-arguments

- Scenario: `A2-S010`
- Fixture: `fixtures/a2/runs/a2_s010_wrong_arguments.json`
- Focus: `argument_fidelity`, `misclassification_probe`
- Local judge: `wrong_arguments`
- Offline LLM reference: `ignored_tool_result`
- Status: `open`

Reviewer note:

`sample-a2-s010-wrong-arguments` is a calibration disagreement. The deterministic local judge identifies a wrong tool argument, while the offline semantic reference frames the final answer as ignoring the tool result. Keep this as a regression seed until reviewed Ashr grading or audited live LLM evidence decides whether this is a judge-boundary issue or an expected semantic ambiguity.

Regression assertion:

Keep local `primary_failure_class=wrong_arguments` visible when semantic/LLM judge reports `ignored_tool_result` for the same case.
