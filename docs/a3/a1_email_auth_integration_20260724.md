# A1 Email Authentication Integration - 2026-07-24

## Plain-language status

A1 now owns the secure backend steps for email registration and email login.
A3 now owns the matching browser form and calls those exact A1 endpoints. A3
never reads access or refresh cookie values.

This closes the previous missing `challenge_id` browser-context blocker. It
does not make the complete hosted identity product production-ready.

## Integrated A1 source

- Source branch: `origin/codex/a1-local-sdk-runner`
- Source commit: `780e94fc9de29563e70cb41a5855a679780601fc`
- Integration commit: merge commit `56037ed`
- A1 database authority: migration 025
- A1 OAuth database contract: migration 026

## A3 browser flow

1. Registration calls `POST /v1/identity/registration/email/begin`.
2. Login calls `POST /v1/identity/login/email/begin`.
3. A3 keeps only the returned short-lived `challenge_id` and `intent_id` in
   React component state. They are not written to local or session storage.
4. The user enters the six-digit proof received by email.
5. Registration calls `POST /v1/identity/registration/email/complete` with
   `challenge_id`, `intent_id`, `proof`, and `display_name`.
6. Login calls `POST /v1/identity/login/email/complete` with `challenge_id`,
   `intent_id`, and `proof`.
7. A3 accepts only a successful same-origin redirect ending at `/console`.
8. A1 owns the encrypted intent cookie and access/refresh HttpOnly cookies.
9. A3 then changes the visible route to `/overview`; this is only navigation.
   Server-side route protection still depends on the cookie identity-read
   contract listed below.

## Security requirements

- The webapp and A1 must be exposed through the same HTTPS origin.
- `/v1/*` must be routed to A1 by a trusted reverse proxy.
- `/console` must be routed to the A3 product console.
- Plain HTTP is read-only demo mode and cannot enable real email auth.
- Email, proof, cookies, SMTP authorization, API keys, and bearer material must
  never enter logs, fixtures, documentation, or browser storage.

## Remaining backend/deployment work

### Required for a complete email-login product

- Add a browser-cookie identity read contract. The current `GET /v1/me`
  implementation still expects explicit session/bearer headers and A3 cannot
  safely construct those from HttpOnly cookies.
- Add a browser-cookie logout/revoke contract that clears both access and
  refresh cookies server-side.
- Put A1 and A3 behind one trusted local or hosted HTTPS reverse proxy.
- Run PostgreSQL migrations 001-026 and the A1 API with production identity
  configuration.
- Configure the transactional verification-delivery worker and SMTP through
  secret references. No SMTP secret exists in this A3 worktree.
- Add server-side protection for A3 console and API routes after cookie-based
  session read exists. Client-side redirects alone are not an authorization
  boundary.

### Required for Google/GitHub first login

- Production Go PostgreSQL first-login coordinator.
- Provider adapter and external opaque-vault wiring.
- Public start/callback orchestration with PKCE, state, and nonce closure.
- Final secure browser session handoff and adversarial replay/scope tests.

A3 keeps the Google and GitHub first-login buttons disabled until these items
are complete.

## Local restart behavior

The local website is served by a Node process on `127.0.0.1`. Windows stops
that process during reboot, so the URL cannot remain available by itself.

`start-ashr-demo.cmd` now:

- rebuilds the Webapp when source files are newer than exported HTML;
- starts the local server only when it is not already healthy;
- polls `/__health` before opening the page;
- writes process logs and PID metadata under ignored `.local-runtime/`;
- opens the login page at
  `http://127.0.0.1:4174/apps/webapp/out/login/`.

`scripts/install-local-demo-shortcut.ps1` creates the desktop shortcut
`Ashr Local Demo.lnk`. After reboot, double-clicking that shortcut restores the
read-only local product demo.

## Verification evidence

- Focused A3 auth/report/dashboard Node contracts: `124 passed`.
- Focused A1 Go browser identity/OAuth contracts: passed across the SDK, API,
  identity-delivery, and worker command packages.
- Next.js TypeScript check: passed.
- Next.js static production build: 15 pages generated.
- Focused Playwright API Reference/registration flow: `1 passed`.
- CL hygiene and commercial guards: passed with zero findings, advisories, or
  blockers.
- In-app browser check: login page loaded, correct A1 source displayed, no
  document-level horizontal overflow.
- Real account creation was not attempted because the current worktree lacks
  the required same-origin HTTPS/PostgreSQL/SMTP runtime.
