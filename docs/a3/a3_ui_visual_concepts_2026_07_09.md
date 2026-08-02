# A3 UI Visual Concepts - 2026-07-09

This is a clean-room visual exploration for the A3 Dashboard / Product Console.
It does not copy external website source code, private frontend code, images, or
assets.

## Security Note

The first visual concept pass was generated without using an external design
LLM. A later production-polish pass called the locally configured design LLM
through `A3_DESIGN_LLM_*` environment variables and wrote only sanitized design
guidance to `docs/a3/a3_design_llm_review_2026_07_09.md`.

No API key, token, cookie, account value, source code, or private ReleaseFoundry data was
printed, written, committed, or sent in the prompt.

## Preview File

- `apps/dashboard/ui-concepts.html`

This file contains four original dashboard style directions.

## Screenshots

- `docs/screenshots/a3-ui-concept-command-console-2026-07-09.png`
- `docs/screenshots/a3-ui-concept-ops-matrix-2026-07-09.png`

## Concepts

### Concept A - Quiet Review Console

Best fit:

- Main A3 dashboard direction.
- Reviewer workflow.
- Enterprise evidence review.
- Low-noise SaaS console.

Why it works:

- Clear hierarchy.
- Low visual risk.
- Good for long evidence text.
- Easy to merge into current dashboard CSS.

Tradeoff:

- Less dramatic than the other options.

### Concept B - Engineering Command Console

Best fit:

- Release Gate.
- Trace Timeline.
- GitHub/CI gate.
- Audit bundle and event outbox areas.

Why it works:

- Strong engineering feel.
- Good for trace/event/log surfaces.
- Makes blocked release state feel serious.

Tradeoff:

- Full dark mode may be tiring for long report review.

### Concept C - Commercial Ledger Dashboard

Best fit:

- SaaS demo.
- Usage and billing readiness.
- Report Center.
- Trust and management overview.

Why it works:

- Looks closest to a polished commercial product.
- Stronger first impression for group lead / mentor demo.
- Better for showing ReleaseFoundry as a SaaS business, not only an eval viewer.

Tradeoff:

- The hero-style top section should be toned down if merged into the operational
  dashboard.

### Concept D - Ops Matrix Console

Best fit:

- Incident Replay.
- Observability Replay.
- Failure Clusters.
- Dense release-blocker triage.

Why it works:

- High information density.
- Good for repeated operational review.
- Makes replay/cluster/control gaps easy to scan.

Tradeoff:

- Too dense for a beginner-friendly landing view.

## Recommended Blend

Use Concept A as the base dashboard style, borrow Concept C's commercial polish
for the top summary / Report Center, and borrow Concept B or D only inside
technical sections such as Release Gate, Trace Timeline, EventEnvelope, and
Failure Clusters.

Do not use a full hero landing page. A3 should stay a working SaaS console.

## Production Polish Follow-up

The recommended blend has been applied to the production dashboard stylesheet:

- `apps/dashboard/src/styles.css`

The production pass kept A1/A2 data wiring untouched and focused on product
console polish: lighter SaaS navigation, stronger metric hierarchy, consistent
panel and badge styling, safer mobile layout, and more deliberate media /
trace / failure evidence surfaces.
