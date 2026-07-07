# P3 Official Frontend Notes

## Scope

Observed the public Ashr frontend and attempted to open the authenticated lab frontend. No official code was copied. Notes below are about information architecture, fields, states, and product workflow only.

## Public Site Observation

URL observed:

- `https://ashr.io/`

Visible product concepts:

- `Evals for Agents That Actually Work`
- Datasets
- Test details
- Explore
- Prompts
- SDK
- Full test timelines
- Expected vs. actual, side by side
- Every eval your agent has run
- Scale agent testing by usage

Useful A3 implications:

- A3 should organize around product objects, not only raw traces.
- The important workflow is dataset -> run/test detail -> timeline -> expected vs actual -> export/report.
- Timeline and expected-vs-actual deserve first-class space.
- SDK integration and usage scaling are visible product ideas, so A3 should keep Usage / Quota as a known dashboard area even while the field is not fully wired.

## Authenticated Lab Observation

URL opened:

- `https://lab.ashr.io/`

Observed state:

- Page title: `Ashr Labs`
- URL included `?tab=analysis`
- The browser was not authenticated.
- Visible sign-in actions:
  - Continue with Google
  - Continue with Microsoft
- Visible onboarding concepts:
  - Create your workspace
  - Pick a plan

Result:

- Authenticated dashboard, requests, datasets, runs, run detail, and media evidence screens were blocked by sign-in.
- No forms were submitted.
- No account creation or plan selection was attempted.
- No screenshots containing account data were saved.

## A3 Design Takeaways

- Keep a product console shell, not a landing page.
- Keep top-level objects visible: requests, datasets, runs, analysis, report/export.
- Treat Usage / Quota as a real product panel, but label it as a known gap until A3 has a reliable field source.
- Keep Expected vs Actual beside evidence, not hidden behind a raw JSON-only view.
- Include media evidence as a case-detail panel because real Ashr samples include audio/file fields and VM stream evidence.
- Preserve empty/loading/error states because the official lab can land users in unauthenticated/onboarding states before product data exists.

## Remaining Observation Work

1. Ask a logged-in teammate to open `lab.ashr.io` and confirm the dashboard tabs.
2. Capture private screenshots only if they are sanitized and saved under an approved evidence path.
3. Update A3 page names if official authenticated navigation uses different names for requests/datasets/runs/analysis.

## 2026-07-05 Authenticated Continuation

Current round status:

- The user's Windows app list showed an Edge window titled `Ashr Labs ... Microsoft Edge`, indicating a logged-in or at least Lab-focused browser window was open.
- Direct Windows browser inspection stopped before page content could be read because the automation layer could not verify the current browser URL with enough confidence.
- Codex in-app browser was available, but it did not share the user's Edge login state.
- No screenshots were saved from the logged-in Edge page.
- No forms were submitted and no settings were changed.

New supporting evidence:

- Read-only API calibration succeeded for account/session, datasets, requests, runs, dataset detail, request detail, run detail, and signed-url dataset probes.
- New frontend/API planning docs:
  - `docs/a3/p3_frontend_page_map.md`
  - `docs/a3/p3_frontend_workflow_notes.md`
  - `docs/a3/p3_frontend_field_mapping.md`
  - `docs/a3/p3_frontend_to_a3_mvp_gap.md`
  - `docs/a3/p3_a3_mvp_recommendations.md`

Practical next step:

- Log into `https://lab.ashr.io/` inside the Codex in-app browser, or provide sanitized screenshots of the logged-in Edge pages, then update the page map with direct UI evidence.

## 2026-07-06 Authenticated Lab Observation

The user successfully logged into an isolated Chrome profile launched for this calibration session. Codex connected to that browser through a local CDP debugging port and performed read-only observation. No screenshots were saved, no cookies/tokens were exported, no API key values were read from the page, and no create/delete/submit actions were performed.

Confirmed authenticated navigation:

- Datasets: `https://lab.ashr.io/?tab=analysis`
- Agents: `https://lab.ashr.io/?tab=agents`
- Folders: `https://lab.ashr.io/?tab=folders`
- Analytics: `https://lab.ashr.io/?tab=analytics`
- Usage: `https://lab.ashr.io/?tab=usage`
- Trust: `https://lab.ashr.io/?tab=trust`
- API Keys: `https://lab.ashr.io/?tab=api-keys`
- Team: `https://lab.ashr.io/?tab=team`

Observed page logic:

- Datasets page has search, filter, sort, group, pinned-only, and `New dataset` controls.
- New Dataset opens an 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.
- Analytics page presents product-level health: agents, datasets, graded runs, pass rate, run volume, pass-rate trend, runs by agent, and pass rate by agent.
- Usage page presents Images, Audio, and Files quota counters.
- Trust page presents a public trust/certificate concept with frozen metrics.
- API Keys and Team exist as account/admin pages but are outside A3's MVP scope.
- Settings exposes Theme and Low Power toggles.

Limitations:

- The observed account had no UI-visible datasets, agents, folders, or graded runs.
- Populated run detail, case detail, trace timeline, expected-vs-actual, and native frontend failure labels still need a real hosted run to observe.
