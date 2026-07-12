# A3 Upstream Identity and Trusted Spine Alignment Patch

Date: 2026-07-11

Final remote sync: 2026-07-12

Status: A3 repair complete in source; full closeout verification is recorded
before commit.

## Why this patch exists

The first API Reference and identity pass was calibrated against A1
`ac960bd` and A2 `58fe876`. It exposed the real routes, but the login UI could
still be read as if the Google and GitHub start routes were initial sign-in
routes. A later source review proved that they require an existing trusted A1
session and are account-linking routes.

This patch corrects that product claim and calibrates the Webapp against the
newer draft commits without merging either peer branch.

| Lane | Ref | Read-only calibration SHA | Authority used by A3 |
|---|---|---|---|
| main | `origin/main` | `5dbf4ee` | integrated stable base contained by this branch |
| A1 | `origin/codex/a1-local-sdk-runner` | `c784163` | identity, browser session, run and delivery facts |
| A2 | `origin/dev/g3-a2-calibration` | `47c05e5` | evidence snapshot, grade and release-decision authority |

## Confirmed A1 capability state

| Capability | Source state | A3 behavior |
|---|---|---|
| Email `login` / `recovery` session issue | implemented and tested on A1 draft | document Secure, HttpOnly, SameSite=Strict access and refresh cookies |
| Browser session refresh | implemented and tested on A1 draft | provide a typed same-origin adapter; never read HttpOnly cookie values |
| Refresh rotation, idempotent replay and reuse detection | implemented and tested on A1 draft | document the contract and remain fail-closed on cross-origin previews |
| Google / GitHub credential linking | implemented on A1 draft | keep the adapter explicitly named as account linking |
| Initial Google / GitHub sign-in | not implemented | disable both login buttons and state the blocker |
| Registration browser-session handoff | not implemented | never enter the console as an authenticated user after registration |
| Browser-safe email challenge context | not implemented | keep completion disabled without server-issued context |
| Production HTML email template | not implemented | keep the A3 HTML/text template as a handoff only |

The challenge start response remains a uniform `accepted` envelope without a
`challenge_id`. The A1 SMTP sender still sends only the six-digit code and
expiry. That preserves anti-enumeration behavior but does not give the browser
the context required by the verify request.

## Confirmed A2 capability state

A2 `47c05e5` adds a public-safe trusted evidence and decision spine:

- `a2.evidence_snapshot.v1` freezes evidence completeness, modalities, tool
  sequence, safe artifact hashes, and extractor provenance.
- `a2.decision_ledger.v1` binds the evidence snapshot to versioned judge,
  model, policy, and release-gate facts in an append-only hash chain.
- `a2.trusted_spine_handoff.v1` gives A3 display-safe decision and provenance
  fields.
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
- Added an upstream-delta section that displays the current A1/A2 draft SHAs
  and the exact A2 schema identifiers.
- Upgraded the redacted auth fixture to `a3.auth_contract_snapshot.v2`.

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

1. A1 draft contracts have not merged into `main`.
2. Initial Google/GitHub sign-in and callback-to-Webapp session redirect do
   not exist yet.
3. Registration still lacks a browser-safe mailbox-bound challenge context
   and authenticated session handoff.
4. A3 has a typed refresh adapter but cannot exercise it from a cross-origin
   static preview; production requires one HTTPS origin or a same-origin BFF.
5. A2 trusted-spine data is documented as a draft contract and is not treated
   as stable main data.

## Verification record

- Focused API Reference and Webapp contract tests: `9 pass / 0 fail`.
- TypeScript typecheck and Next.js static production build: passed.
- `git diff --check`: passed.
- Full A3 Node suite: `334 pass / 0 fail`.
- Full Playwright suite: `31 pass / 0 fail` with one-worker isolation.
- Current-main A1/A2 Python suite: `562 pass / 5 skip`, `1013 subtests pass`.
- Latest A1 draft: Go module passed; TypeScript SDK `574 pass / 0 fail`.
- Latest A2 trusted-spine draft: `11 pass / 0 fail`, `29 subtests pass`.
- Commercial CL, hygiene CL, dependency audit, ignore checks, changed-file
  secret scan, and A3-owned-path check: passed.
- A1's draft-only Rust verifier was not run because Cargo is unavailable and
  this A3 patch does not consume that surface.
