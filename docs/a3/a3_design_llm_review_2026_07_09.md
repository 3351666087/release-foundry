# A3 Design LLM Review - 2026-07-09

Status: 200
Model: claude-opus-4-8

Security: the API key was read from local environment only; no key, token, cookie, account info, source code, or private data was sent in the prompt or written here.

## Model Guidance

# 1. CSS Tokens to Adjust

Anchor on "Quiet Review Console" neutrals, borrow Ledger polish via one restrained accent + tighter spacing scale.

1. **`--bg-canvas: #FAFAF9`** and **`--bg-surface: #FFFFFF`** — warm off-white canvas, pure-white raised panels for quiet contrast (avoid pure-gray flatness).
2. **`--border-subtle: #ECEAE6`** / **`--border-strong: #DAD7D1`** — two-tier hairlines; use subtle for table rows, strong for panel edges and section dividers.
3. **`--accent: #3B5BDB`** (single indigo) — reserve for primary actions, active nav, links only. No secondary accent in the review console.
4. **`--accent-weak: #EEF1FD`** — tint for active row/nav backgrounds and selected states.
5. **Status ramp:** `--pass: #2F9E44`, `--fail: #E03131`, `--warn: #F08C00`, `--neutral: #868E96` — desaturate ~10% from default web brights so they read "console," not "alert."
6. **`--font-mono: 'JetBrains Mono', ui-monospace`** scoped to trace/gate/CI/audit only; **`--font-ui: 'Inter', system-ui`** everywhere else.
7. **Type scale:** `--text-xs:12/16`, `--text-sm:13/20`, `--text-base:14/22`, `--text-lg:16`, `--text-xl:20`. Body at 14 = dense SaaS default, not 16.
8. **Spacing base `--space-1:4px` … `--space-6:24px`** on a strict 4px grid; kill arbitrary paddings.
9. **`--radius-sm:6px`, `--radius-md:8px`, `--radius-pill:999px`** — cards at 8, badges pill, inputs 6.
10. **`--shadow-card: 0 1px 2px rgba(20,20,20,.04), 0 1px 1px rgba(20,20,20,.03)`** — one soft elevation token; the Ledger "polish" is subtle depth, not drop shadows.
11. **`--row-height: 40px`** table density token + **`--panel-pad:16px`** so all panels/tables align.
12. **`--tabular: font-variant-numeric: tabular-nums`** utility token applied to all metrics, counts, durations, and scores.

# 2. Production Dashboard Polish

1. **Sidebar:** fixed 240px, grouped sections with 11px uppercase muted labels ("Evaluation," "Analysis," "Admin"); active item = `--accent-weak` bg + 2px left `--accent` bar + `--accent` text. Icons 16px, one muted gray.
2. **Topbar:** 56px sticky bar with breadcrumb (Run › Case › Trace) left, run-context chip (model + timestamp) center-left, global run/env switcher + export right. Hairline bottom border, no shadow.
3. **Metrics row:** 4 KPI cards (Pass Rate, Cases, Avg Latency, Failures) — big tabular-nums value, tiny label above, delta pill vs. prior run (`↑ +3.2%` colored). Equal-width, `--shadow-card`, no icons competing with numbers.
4. **Panels:** standardize a panel header pattern — title (13px semibold) left, action/filter right, hairline divider under, `--panel-pad` body. Every panel identical so the grid reads calm.
5. **Tables:** 40px rows, sticky header (muted 12px uppercase), zebra via `--bg-canvas` on odd rows only, right-align all numeric columns with tabular-nums, hover = `--accent-weak`. Row-click opens detail; whole row is the target.
6. **Badges:** pill status badges with tinted bg + darker text (e.g. pass = `#EBFBEE`/`#2F9E44`), 11px, dot prefix optional. One badge style reused for run status, case verdict, judge grade.
7. **Failure clusters:** horizontal stacked bar or count-ranked list, not a pie. Each cluster row = label + count + share bar in `--fail` tint, click to filter the case table.
8. **Expected vs Actual:** two-column diff with monospace, char/line-level highlight (added `--pass` tint, removed `--fail` tint); collapse matching regions with a "… N unchanged lines" affordance.
9. **Density toggle:** offer Comfortable/Compact (switches `--row-height` 40/32 and `--panel-pad`) — SaaS reviewers live in tables all day.
10. **Empty/loading states:** skeleton rows matching real row height (no spinners), and a real empty-state per panel with one-line guidance + primary action, so a fresh account never shows a blank grid.

# 3. SaaS Admin Polish

1. **Login boundary:** centered 400px card on `--bg-canvas`, product mark, single primary button, SSO/provider buttons secondary; inline field errors, never a top alert bar. Keep it visually separate from the app shell.
2. **Team:** members table with avatar-

