# A3 Visual Rendering Architecture V5

Date: 2026-07-09

## Goal

This round moved the A3 dashboard away from a long, static navigation block and
toward a maintainable visual shell that can later be migrated into a React or
Next.js component app.

The change is visual and structural only. It does not change A1 runner logic,
A1 trace semantics, A2 judge semantics, A2 scores, or A2 failure taxonomy.

## What Changed

- Added `apps/dashboard/src/visual-shell.mjs` as the new visual information
  architecture layer.
- Moved sidebar primary navigation, SaaS product surfaces, and detailed
  workspace rail links into data-driven arrays.
- Reduced the left sidebar to six primary areas:
  `Overview`, `Evaluate`, `Review`, `Reports`, `Admin`, and `Trust`.
- Added a SaaS product surface strip for:
  `Workspace`, `Product Console / Onboarding / Audit`,
  `SaaS Admin / Login / Team / Trust`, `Usage`, `API Keys`, and `Trust`.
- Added a horizontal workspace rail for detailed A3 panels:
  workflow, platform, calibration, release, and output.
- Updated `apps/dashboard/src/app.mjs` so active navigation state is shared
  across the sidebar, product surface strip, and workspace rail.
- Reworked the visual theme from a dark directory-style sidebar into a lighter
  academic SaaS console with restrained accent colors, stable cards, and small
  hover motion.
- Kept all existing dashboard panel ids, data ids, filters, exports, and A1/A2
  data rendering surfaces intact.

## Why This Is Better

- The sidebar is no longer a dry list of every possible panel.
- Product concepts such as login, team, API keys, usage, trust, and reports are
  visible as real SaaS surfaces instead of hidden deep in the page.
- Detailed areas still exist, but they live in a compact rail that can scale.
- The visual shell is now closer to a component boundary: future React/Next.js
  migration can reuse the same navigation configuration.
- Tests now understand both old HTML navigation targets and new configuration
  driven navigation targets.

## Clean-Room Design Inputs

The visual rhythm used only sanitized layout principles from the local
clean-room video portal notes:

- light canvas
- dense but clear content rhythm
- short chip rail
- stable card dimensions
- hover translate without layout shift
- no copied source code, brand assets, text, media, tokens, cookies, or account
  data

## A1/A2 Compatibility

- A1 RunResult, Trace, Observation, ToolCall, and runner fixtures remain
  unchanged.
- A2 Scenario, Judge, GradeResult, score, pass/fail, and failure taxonomy
  remain unchanged.
- A3 still renders existing normalized run/case/trace/grade/report data.
- Navigation refactor only changes how users reach sections, not how evidence is
  computed.

## Evidence

- `docs/screenshots/a3-dashboard-visual-rendering-v5-first-viewport-2026-07-09.png`
- `docs/screenshots/a3-dashboard-visual-rendering-v5-mobile-first-viewport-2026-07-09.png`

## Validation

- `node --test tests/a3/dashboard_wiring.test.mjs`
- `node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_api_server.test.mjs`
- `npm.cmd run test:e2e`
- `python scripts/cl_guard.py hygiene`
- `python scripts/cl_guard.py commercial`
- `git diff --check`
