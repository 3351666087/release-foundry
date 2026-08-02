# A2 Case Book

This case book is the reviewer-facing companion to `fixtures/a2/results/a2_case_book.json`.

It records calibration disagreements and explicitly approved public-safe incident
regressions. Both remain visible until reviewed ReleaseFoundry grading or audited live LLM
evidence resolves the boundary.

## C5 Maturity Gate

- Calibration cases: `6`
- Local-vs-LLM comparable cases: `6`
- Local-vs-LLM mismatch candidates: `1`
- Promoted regression cases: `1`
- Reviewed external evidence cases: `0`
- Missing ReleaseFoundry grading observations: `6`
- Mature target: `3` reviewed disagreement regressions
- Current status: `seed`

C5 remains partial because 2 more reviewed disagreement regressions are needed, and the regression set still needs reviewed ReleaseFoundry grading or audited semantic evidence before the case book and replay suite should be called mature.

## Incident Regression Candidates

Production incidents can enter the case-book review queue through `fixtures/a2/results/a2_incident_regression_candidates.json`.

The current public-safe candidate is `prod-inc-2026-07-support-status-retry`, mapped to `sample-a2-s041-poor-retry-recovery` / `A2-S041`. It is replayable through `fixtures/a2/runs/a2_s041_poor_retry_recovery.json` and preserves local `primary_failure_class=poor_failure_recovery`.

This candidate is not counted as a mature C5 replay case yet. It is not promoted
automatically. The owner must submit an auditable decision through
`services.judge.casebook.promote_incident_candidates_to_case_book(...)`:

```python
promoted = promote_incident_candidates_to_case_book(
    case_book_report,
    incident_candidates_report,
    [{
        "case_id": "sample-a2-s041-poor-retry-recovery",
        "decision": "approved",
        "reviewer_receipt": "sha256:<64 lowercase hex>",
        "reviewed_at_unix_ms": 1784700000000,
        "source_incident_candidates_hash": incident_candidates_report["artifact_hash"],
        "candidate_hash": stable_hash(
            incident_candidates_report["candidates"][0]
        ),
        "evidence_refs": [
            "docs/evidence/private_refs/a2_case_book_owner_review.redacted.json",
        ],
    }],
)
```

This approval only makes the candidate eligible for deterministic replay. It does
not count as reviewed ReleaseFoundry or audited live semantic evidence, so the C5 maturity
gate must remain `seed` until those external evidence rows are present.

The owner decision is bound to both the complete candidate-report artifact and
the exact selected candidate content. The resulting `metadata.promotion_audit`
records those hashes and the decision outcome. Invalid reviewer receipts, stale
or mismatched hashes, duplicate decisions, unknown candidate ids, unsafe
candidates, and missing replay fixtures fail closed rather than silently
promoting or passing.

## Regression: sample-a2-s010-wrong-arguments

- Scenario: `A2-S010`
- Fixture: `fixtures/a2/runs/a2_s010_wrong_arguments.json`
- Focus: `argument_fidelity`, `misclassification_probe`
- Local judge: `wrong_arguments`
- Offline LLM reference: `ignored_tool_result`
- Status: `open`

Reviewer note:

`sample-a2-s010-wrong-arguments` is a calibration disagreement. The deterministic local judge identifies a wrong tool argument, while the offline semantic reference frames the final answer as ignoring the tool result. Keep this as a regression seed until reviewed ReleaseFoundry grading or audited live LLM evidence decides whether this is a judge-boundary issue or an expected semantic ambiguity.

Regression assertion:

Keep local `primary_failure_class=wrong_arguments` visible when semantic/LLM judge reports `ignored_tool_result` for the same case.
