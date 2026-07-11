# A3 Visual Rebuild and A1/A2 Evidence Spine

Date: 2026-07-11

## Scope

This round rebuilt the A3 dashboard visual system and made the A1/A2 handoff a
first-class product surface. It did not change A1 runner behavior, A2 judge
semantics, release policy authority, or any hosted mutation boundary.

## Clean-room design references

Public pages inspected for high-level visual grammar:

- `https://antonskvor.webflow.io/`
- `https://dribbble.com/AntonSKV`
- `https://dribbble.com/shots/25858512-AI-company-website-concept`

The implementation uses only general design observations:

- black and warm-white contrast;
- large geometric uppercase display type;
- numbered navigation and chapter markers;
- thin rules, controlled whitespace, and asymmetric composition;
- compact metadata labels and restrained command pills;
- deliberate hover/focus states and reduced-motion support.

No source code, CSS, HTML, images, particles, 3D assets, fonts, copy, branding,
or proprietary implementation from the reference sites was copied. The A3
HTML and CSS were authored from scratch around the existing product contracts.

## A1/A2 evidence spine

The new `a3.a1_a2_evidence_spine.v1` contract turns the cross-lane handoff into
four visible stages:

| Stage | Owner | Inputs | A3 presentation |
|---|---|---|---|
| Capture | A1 | RunResult, Observation, TraceEvent, ToolCall | run/case counts, trace completeness, observations, tool calls |
| Evaluate | A2 | GradeResult, JudgeResult, RubricResult, failure taxonomy | judge count, pass rate, score, failure classes |
| Gate | A2 | ReleaseGate and ReleasePolicy | decision, risk, blockers, warnings, evidence refs |
| Operate | A3 | review workflow, reports, provenance | reviewer records, report count, downstream release actions |

Three handoff rows expose linked and unresolved evidence between A1, A2, the
release gate, and A3. The contract never embeds raw upstream payloads and never
recomputes A2 policy.

The latest locally available peer references were:

- `origin/main`: `5dbf4ee`
- A1 draft `origin/codex/a1-local-sdk-runner`: `ac960bd`
- A2 draft `origin/dev/g3-a2-calibration`: `58fe876`

A1 identity verification and A2 multimodal API smoke are shown only as draft
watch signals. `draft_contracts_are_authoritative` remains `false`; both must
merge to `main` before A3 can make production claims.

## Product layout

The dashboard now uses six stable top-level areas with collapsible children:
Overview, Evaluate, Review, Reports, Admin, and Trust. Every existing product
surface remains reachable through a child link, including official calibration,
incident replay, observability replay, regression, billing, and cloud controls.

The page is divided into numbered chapters for evidence, operations, release
control, report output, and case inspection. Existing DOM ids are preserved so
API wiring, exports, filters, and tests continue to work.

The SaaS Runtime default view was compacted from 941 px to 586 px at the tested
desktop width. All eight detailed API, DB, migration, usage, billing, outbox,
and guardrail disclosures remain available.

## Implementation surfaces

- `services/report/a3_a1_a2_evidence_spine.mjs`
- `apps/dashboard/src/components/a1-a2-evidence-spine.mjs`
- `services/report/a3_store.mjs`
- `services/report/a3_api_server.mjs`
- `apps/dashboard/index.html`
- `apps/dashboard/src/visual-shell.mjs`
- `apps/dashboard/src/styles.css`
- `apps/dashboard/src/app.mjs`

API availability:

- dashboard payload key: `a1_a2_evidence_spine`
- read endpoint: `GET /api/a3/a1-a2/evidence-spine`
- authorization: existing `read_schema_drift` auditor boundary

## Verification

- Full A3 Node suite: `324 pass / 0 fail`.
- Full Playwright suite: `21 pass / 0 fail`.
- Focused A1/A2 Python compatibility: `175 pass / 0 fail`, `992 subtests pass`.
- Commercial CL guard: passed, 0 blockers, 0 advisories.
- Hygiene CL guard: passed, 0 findings.
- `git diff --check`: passed.
- In-app desktop check: 32 API-backed cases, evidence spine rendered, no
  horizontal overflow, and no status/index overlap.
- In-app 390 x 844 check: two-column navigation, no horizontal overflow, and
  evidence/headline bounds remain inside the viewport.

Current screenshots:

- `docs/screenshots/a3-visual-system-desktop.png`
- `docs/screenshots/a3-visual-system-mobile-390x844.png`
- `docs/screenshots/a3-runtime-contract-layout-api-backed-2026-07-11.png`

## Remaining work

1. Migrate the tall single-page console into route-level React/Next.js product
   pages while preserving the current API and DOM behavior contracts.
2. Replace draft identity and multimodal watch signals only after their A1/A2
   contracts merge to `main`.
3. Connect hosted identity, durable review/report mutations, and live billing
   only through A1-owned authenticated executors and A2-verified policy state.

GitHub fetch failed during this round because the local machine could not reach
`github.com:443`. Therefore the hashes above are the latest locally available
remote references, not proof of a newer remote state.
