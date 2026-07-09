# A3 UI Visual Concepts V2 - 2026-07-09

This round responds to visual feedback that the first production polish still
felt too plain.

The goal was to try stronger, current SaaS dashboard directions while staying
clean-room: no external source code, private frontend code, copied assets,
logos, screenshots, or brand styling files were used.

## Public Reference Directions

- Linear: agent-oriented product workflow language and fast triage feel.
- Vercel: redesigned dashboard navigation, project filtering, and mobile-first
  navigation ideas.
- Supabase: database/auth/storage studio mental model.
- Retool: dense internal ops table and admin workflow mental model.

These references informed layout and product mood only.

## Preview File

- `apps/dashboard/ui-concepts-v2.html`

## Screenshots

- `docs/screenshots/a3-ui-concepts-v2-overview-2026-07-09.png`
- `docs/screenshots/a3-ui-concept-v2-linear-vercel-2026-07-09.png`
- `docs/screenshots/a3-ui-concept-v2-supabase-2026-07-09.png`
- `docs/screenshots/a3-ui-concept-v2-ledger-2026-07-09.png`
- `docs/screenshots/a3-ui-concept-v2-retool-2026-07-09.png`

## Concepts

### Concept E - Linear / Vercel Release Console

Best fit:

- Main A3 production dashboard.
- Release gate, run triage, and report review.
- Student demo where the first screen should look like a real SaaS console.

Why it works:

- Dark left navigation makes the product feel more finished.
- Dark top release context focuses attention on the current run.
- White evidence cards keep long A1/A2 data readable.
- The structure matches A3's real job: review release evidence, not present a
  marketing page.

### Concept F - Supabase Studio Workbench

Best fit:

- Future artifact storage, DB, media custody, and developer settings screens.

Why it was not chosen for production:

- Full dark mode makes long report review harder.
- It over-emphasizes DB objects, while A3's main job is triage/report review.

### Concept G - Commercial Ledger Dashboard

Best fit:

- Billing, usage, hosted report center, enterprise readiness, and customer
  summary pages.

Why it was not chosen for production:

- Too sales/report oriented for the main evaluation workflow.

### Concept H - Retool Ops Grid

Best fit:

- Internal admin queue, reviewer workflow, audit trail, and dense operations.

Why it was not chosen for production:

- Good for internal tools, but less polished for mentor demo screenshots.

## Production Decision

Concept E was applied to `apps/dashboard/src/styles.css`.

Changed visual direction:

- Dark sidebar.
- Dark release-context topbar.
- Cleaner white evidence cards.
- Softer metric state borders instead of heavy colored bars.
- Mobile nav retained as horizontal scroller.

No A1 or A2 logic changed.
