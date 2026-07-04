# A2 Case Book

This case book is the reviewer-facing companion to `fixtures/a2/results/a2_case_book.json`.

It records calibration disagreements that should remain visible until reviewed Ashr grading or audited live LLM evidence resolves the boundary.

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
