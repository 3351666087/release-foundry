# A3 Upstream Identity and Trusted Spine Alignment Patch

Date: 2026-07-11

Final remote sync: 2026-07-12

Status: A3 repair recalibrated against merged `main` `7dd14d7`.

## Why this patch exists

The first API Reference and identity pass was calibrated against A1
`ac960bd` and A2 `58fe876`. It exposed the real routes, but the login UI could
still be read as if the Google and GitHub start routes were initial sign-in
routes. A later source review proved that they require an existing trusted A1
session and are account-linking routes.

This patch corrects that product claim. A1 `c784163` and A2 `8cd1d4f` have
since entered `main` through integration commit `7dd14d7`, so A3 now treats
their published contracts as main authority while preserving every remaining
product blocker.

| Lane | Ref | Read-only calibration SHA | Authority used by A3 |
|---|---|---|---|
| main | `origin/main` | `7dd14d7` | integrated A1/A2/A3 base |
| A1 | `main` source commit | `c784163` | identity, browser session, run and delivery facts |
| A2 | `main` source commit | `8cd1d4f` | evidence snapshot, grade and release-decision authority |

## Confirmed A1 capability state

| Capability | Source state | A3 behavior |
|---|---|---|
| Email `login` / `recovery` session issue | implemented and merged to main | document Secure, HttpOnly, SameSite=Strict access and refresh cookies |
| Browser session refresh | implemented and merged to main | provide a typed same-origin adapter; never read HttpOnly cookie values |
| Refresh rotation, idempotent replay and reuse detection | implemented and merged to main | document the contract and remain fail-closed on cross-origin previews |
| Google / GitHub credential linking | implemented and merged to main | keep the adapter explicitly named as account linking |
| Initial Google / GitHub sign-in | not implemented | disable both login buttons and state the blocker |
| Registration browser-session handoff | not implemented | never enter the console as an authenticated user after registration |
| Browser-safe email challenge context | not implemented | keep completion disabled without server-issued context |
| Production HTML email template | not implemented | keep the A3 HTML/text template as a handoff only |

The challenge start response remains a uniform `accepted` envelope without a
`challenge_id`. The A1 SMTP sender still sends only the six-digit code and
expiry. That preserves anti-enumeration behavior but does not give the browser
the context required by the verify request.

## Confirmed A2 capability state

A2 `8cd1d4f` publishes a public-safe trusted evidence and decision spine:

- `a2.evidence_snapshot.v1` freezes evidence completeness, modalities, tool
  sequence, safe artifact hashes, and extractor provenance.
- `a2.decision_ledger.v1` binds the evidence snapshot to versioned judge,
  model, policy, and release-gate facts in an append-only hash chain.
- `a2.trusted_spine_handoff.v1` gives A3 display-safe decision and provenance
  fields.
- Evidence snapshots and decision ledgers bind the same required five-field
  scope: `organization_id`, `tenant_id`, `workspace_id`, `project_id`, and
  `environment_id`.
- The snapshot exposes `scope_complete` and `validation_errors`, and the
  trusted-spine builder directly validates A1 RunResult cases before release
  evidence is accepted.
- A3 may display decision, review status, evidence completeness, modalities,
  provenance hash, and chain verification.
- A3 must not recompute a grade, rewrite a decision record, or treat a missing
  or invalid chain as release-ready.

## A3 product changes

- Added explicit capability metadata in `apps/webapp/lib/auth-api.ts`.
- Renamed the provider adapter to `startOAuthAccountLinking` so it cannot be
  mistaken for initial sign-in.
- Disabled Google and GitHub sign-in controls while A1 reports initial sign-in
  as unavailable.
- Added a typed same-origin browser-session refresh adapter with
  `credentials: include` and a generated `Idempotency-Key`.
- Added the refresh endpoint to `/api-reference`.
- Added an upstream-main section that displays the current A1/A2 source SHAs,
  merge state, exact A2 schema identifiers, and five required scope fields.
- Upgraded the redacted auth fixture to `a3.auth_contract_snapshot.v3` and
  removed the obsolete `a1_auth_not_in_main` blocker.

## Endgame-plan alignment

This work stays in the A3 Product Web lane defined by
`docs/strategy/large-saas-a1-a2-a3-full-plan.md`:

- TypeScript, React, and Next.js remain the product-web mainline.
- A1 keeps identity, session, OAuth, delivery, and runner authority.
- A2 keeps grade, failure taxonomy, release policy, and decision authority.
- A3 presents typed downstream capability state and fails closed.
- No A1/A2 implementation or schema was modified.
- No cookie, token, code, email, provider secret, API key, or account payload
  was read or persisted.

## Still blocked

1. Initial Google/GitHub sign-in and callback-to-Webapp session redirect do
   not exist yet.
2. Registration still lacks a browser-safe mailbox-bound challenge context
   and authenticated session handoff.
3. A3 has a typed refresh adapter but cannot exercise it from a cross-origin
   static preview; production requires one HTTPS origin or a same-origin BFF.

## Verification record

- Focused API Reference and Webapp contract tests: `9 pass / 0 fail`.
- TypeScript typecheck and Next.js static production build: passed.
- `git diff --check`: passed.
- Full A3 Node suite: `334 pass / 0 fail`.
- Full Playwright suite: `31 pass / 0 fail` with one-worker isolation.
- Current-main A1/A2 Python suite: `562 pass / 5 skip`, `1013 subtests pass`.
- A1 source commit now in main: Go module passed; TypeScript SDK `574 pass / 0 fail`.
- A2 trusted-spine source commit now in main: `11 pass / 0 fail`, `29 subtests pass`.
- Commercial CL, hygiene CL, dependency audit, ignore checks, changed-file
  secret scan, and A3-owned-path check: passed.
- A1's Rust verifier was not run because Cargo is unavailable and
  this A3 patch does not consume that surface.

### Merged-main addendum, 2026-07-12

- Latest-main A3 Node suite: `334 pass / 0 fail`.
- Latest-main A2 suite: `185 pass / 0 fail`, `1042 subtests pass`.
- Latest-main trusted-spine focus: `7 pass / 0 fail`.
- Focused API Reference/Webapp contracts: `9 pass / 0 fail`.
- TypeScript typecheck and Next.js production static build: passed.
- Full Playwright suite: `31 pass / 0 fail`, including API-aware Webapp routes
  `6 pass / 0 fail`.
- Webapp dependency audit: `0 vulnerabilities`.
- Standard Git HTTPS remained unavailable, so the official GitHub API archive
  was used only as a temporary test sandbox. A proper branch replay still
  requires standard fetch before Git publication.
