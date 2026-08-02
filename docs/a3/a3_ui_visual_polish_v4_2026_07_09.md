# A3 UI Visual Polish V4 - 2026-07-09

This round responds to feedback that V3 became too colorful and still did not
feel refined enough.

## Wider Reference Scan

References were used only for layout and interaction ideas:

- Bilibili: content-density, horizontal navigation, and card-feed rhythm. The
  fetchable page in this environment returned a browser-upgrade page, so this
  was treated as limited category inspiration only.
- Apple: restrained hierarchy, clean whitespace, and premium simple surfaces.
- Notion: calm workspace layout, section cards, and agent/workflow language.
- Raycast: modern dark productivity shell and fast command-console feel.
- Linear / Vercel: release-console structure from the previous round.

No external source code, screenshots, logos, images, assets, brand tokens, or
private frontend files were copied.

## V4 Decision

V4 keeps the stronger V2 dark-sidebar product feel, removes the V3 loud color
gradient, and invests in detail:

- Dark premium sidebar.
- Restrained dark release-context topbar.
- White/soft-gray evidence panels for readability.
- Subtle state strips instead of large colorful cards.
- Smooth anchor scrolling.
- Nav active-state updates on click and while scrolling.
- Direct hash-link active-state repair for links such as `#console`.
- Non-floating overview topbar so anchor navigation does not hide section
  content.
- Lightweight section focus animation after navigation.
- Button, panel, case, and triage hover transitions.
- Reduced-motion support.

## Files

- `apps/dashboard/src/styles.css`
- `apps/dashboard/src/app.mjs`
- `docs/screenshots/a3-dashboard-visual-polish-v4-mobile-2026-07-09.png`
- `docs/screenshots/a3-dashboard-v4-console-anchor-no-overlap-2026-07-09.png`

## Anchor Navigation Fix

User testing showed the previous sticky overview topbar could cover the top of
the target section after clicking sidebar links. V4 now keeps the overview
topbar in normal document flow and sets a smaller section scroll margin.

Playwright evidence:

- Opening `?source=p3-official-demo#console` places `#console` at the top of the
  viewport without overview-topbar overlap.
- The active sidebar item becomes `Console` on direct hash load.

## A1 / A2 Safety

This is an A3 UI-only round:

- No A1 runner, SDK, RunResult, Trace, Observation, or ToolCall semantics changed.
- No A2 Scenario, Judge, GradeResult, score, pass/fail, or failure-taxonomy
  semantics changed.
- Dashboard data sources still include mock, API-backed mock, raw A1, raw A2,
  P3 media, and P3 official demo fixtures.
