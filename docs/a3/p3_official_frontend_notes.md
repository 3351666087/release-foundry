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
