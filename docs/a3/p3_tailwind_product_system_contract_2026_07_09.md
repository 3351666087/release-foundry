# P3 Tailwind Product System Contract - 2026-07-09

Role: A3 Tailwind/Product-System worker.

Scope: introduce a testable Tailwind product-system contract for the A3 dashboard, report, and E2E surfaces without changing runtime code, installing dependencies, running live APIs, or reading `.env.local`.

## Purpose

`tailwind.config.ts` is now the product-system anchor for A3 commercial UI work. It gives A3 a shared token contract for dashboard density, report/readback evidence, review workflow, SaaS admin, and hosted report surfaces instead of relying only on hand-written CSS conventions.

This is not a visual rewrite. It is a contract that future A3 UI work can consume when the dashboard migrates from custom CSS toward a Tailwind-backed product system.

## Content Boundary

The Tailwind content globs intentionally cover:

- A3 dashboard app shell: `apps/dashboard/index.html`
- A3 dashboard modules/components: `apps/dashboard/src/**/*`
- A3 report builders and API-facing report surfaces: `services/report/**/*`
- A3 unit contract tests: `tests/a3/**/*`
- A3 Playwright/E2E test source: `tests/e2e/**/*`
- A3 docs and product-system evidence: `docs/a3/**/*`
- A3 redacted fixtures and report artifacts: `fixtures/a3/**/*`

The globs do not include `.env.local`, `docs/evidence/private_refs/`, `.secrets/`, raw private evidence, or generated browser trace folders.

## Token Contract

The config defines tokens for:

- Semantic colors: `canvas`, `surface`, `ink`, `line`, `accent`, `evidence`, `success`, `warning`, `danger`, and `review`.
- Spacing: `a3-field`, `a3-row`, `a3-panel`, `a3-section`, `a3-gutter`, `a3-rail`, and `a3-touch`.
- Radius: `control`, `card`, `panel`, and `modal`.
- Font families: `sans` and `mono`.
- Font sizes: `a3-caption`, `a3-body`, `a3-label`, `a3-title`, and `a3-metric`.

The palette deliberately avoids a one-color purple/blue theme. Evidence can use blue, but approval, warning, danger, success, review, canvas, and surface states have distinct semantic hues.

## API Contract

Tailwind is a frontend styling contract only. It does not create a new API, but it supports these existing and future A3 API surfaces:

- `GET /api/a3/dashboard`
- `GET /api/a3/reports`
- `GET /api/a3/report-center`
- `GET /api/a3/releases/:releaseId/evidence-summary`
- `POST /api/a3/releases/:releaseId/readbacks`
- `GET /api/a3/admin/console`

API responses should keep using A1/A2 evidence fields and A3 report state. Tailwind classes should not encode business decisions. Release gate status, readback status, usage counts, and approval state must come from API payloads, not from color names.

## DB Contract

No DB migration is introduced in this round. The product-system tokens are allowed to style existing A3 DB-backed surfaces, including:

- `release_evidence_summaries`
- `release_evidence_snapshots`
- `release_evidence_readbacks`
- `review_workflow_records`
- `saas_admin_action_requests`
- `artifact_registry_entries`
- `usage_ledger_entries`

Future DB-backed theme preference must be tenant-scoped and should store a small display preference such as `theme_mode` or `density_mode`, not raw CSS, arbitrary class names, or customer-provided style payloads.

## Event Contract

No new event is emitted by the Tailwind config. Future product-system changes can emit audit-safe events only when they affect persisted user or tenant preference:

- `product_system.theme_preference_changed`
- `product_system.density_preference_changed`
- `product_system.report_skin_exported`

Event payloads must contain ids, token version, old/new preference names, actor id, request id, and redaction status. They must not contain raw CSS, secrets, cookies, tokens, or private evidence.

## Artifact Contract

The product-system artifact set is:

- `tailwind.config.ts`
- `postcss.config.mjs`
- `docs/a3/p3_tailwind_product_system_contract_2026_07_09.md`
- `tests/a3/tailwind_boundary_contract.test.mjs`

These artifacts are public-safe and can be referenced by a future A3 artifact registry entry with `artifact_type=product_system_contract`. Generated CSS is not checked in by this round and should not become an audit artifact unless it is built reproducibly and scanned by the export firewall.

## Tenant / Auth / RBAC / Usage / Audit Impact

- Tenant: tokens are global defaults. Tenant-specific theme or density preference must be stored by organization/project scope before SaaS claims.
- Auth: no auth route changes are made. A user must not gain access to a report, admin panel, or release evidence because a Tailwind class renders it visible.
- RBAC: UI styling must not replace permission checks. Admin, billing, Trust, API-key, review, and readback actions stay governed by A3 API/store contracts.
- Usage: Tailwind itself is not billable. If future generated report skins become export products, usage should be metered as `report_exports` or a new explicit product-system export meter.
- Audit: token changes are code-reviewed artifacts. Runtime theme preference changes, if added later, should append audit events and never store raw CSS.

## A1 / A2 / A3 Integration

A1 integration:

- A1 remains the source for run, case, trace, worker, usage, and artifact evidence.
- Tailwind tokens may style A1-derived run status, trace completeness, worker retry/dead-letter state, usage meter counts, and verifier state.
- Tailwind tokens must not invent A1 authority. A failed A1 verifier remains failed even if a UI badge uses `success`.

A2 integration:

- A2 remains the source for grade results, canonical failure class, judge evidence, release policy, scenario selection, and commercial readiness.
- Tailwind tokens may style A2 severity, blocker, warning, reviewed, and evidence states.
- Tailwind tokens must not reinterpret A2 `primary_failure_class`, score scale, or release gate decision.

A3 integration:

- A3 owns the product console, review workflow, report center, GitHub gate, hosted reports, SaaS admin console, and customer-facing evidence surfaces.
- This product system gives those surfaces a shared density and semantic state language while keeping source authority in A1/A2/A3 API contracts.

## Verification

The contract test is:

```powershell
node --test tests/a3/tailwind_boundary_contract.test.mjs
```

It reads the Tailwind config, PostCSS config, and this document, then checks:

- A3 dashboard/app/report/e2e content globs exist.
- Semantic color, spacing, radius, and font tokens exist.
- The document names API, DB, event, artifact, tenant, auth, RBAC, usage, audit, A1, A2, and A3.
- No high-confidence secret patterns are present.

This test is source-only and does not require Tailwind, PostCSS, browser runtime, live APIs, or private evidence.
