# A1 Email Authentication Integration - 2026-07-24

## Plain-language status

A1 now owns the secure backend steps for email registration and email login.
A3 now owns the matching browser form and calls those exact A1 endpoints. A3
never reads access or refresh cookie values.

This closes the previous missing `challenge_id` browser-context blocker. The
same branch now also contains a verified local PostgreSQL, Mailpit, and HTTPS
identity closure. It does not make the hosted identity product production-ready.

## Integrated A1 source

- Source branch: `origin/agent/a1-local-sdk-runner`
- Initial email source commit: `780e94fc9de29563e70cb41a5855a679780601fc`
- Latest integrated A1 commit: `689799750a9a092ffb3ce92d17100256310bd2e8`
- Integration commit: merge commit `56037ed`
- A1 database authority: migration 025
- A1 OAuth database contract: immutable migration 026 plus forward upgrade 027

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
9. A3 then changes the visible route to `/overview` and checks `GET /v1/me`
   through the HttpOnly access cookie before rendering the console.
10. Logout calls `POST /v1/identity/sessions/revoke`, revokes the durable
    PostgreSQL session family, clears both cookies, and returns to `/login`.

## Security requirements

- The webapp and A1 must be exposed through the same HTTPS origin.
- `/v1/*` must be routed to A1 by a trusted reverse proxy.
- `/console` must be routed to the A3 product console.
- Plain HTTP is read-only demo mode and cannot enable real email auth.
- Email, proof, cookies, SMTP authorization, API keys, and bearer material must
  never enter logs, fixtures, documentation, or browser storage.

## Local real-login closure

The local development stack now provides:

- PostgreSQL migrations 001-026 plus one seeded organization, workspace, and project;
- local-only verification delivery to Mailpit;
- Caddy same-origin HTTPS at `https://localhost:4443`;
- browser-cookie `GET /v1/me`;
- tenant-scoped durable `POST /v1/identity/sessions/revoke`;
- Secure, HttpOnly, SameSite=Strict access and refresh cookies;
- an A3 identity gate, authenticated account label, and logout action.

The in-app browser created a redacted local test account, completed registration
and a later independent email-login challenge, refreshed the console, read
`/v1/me`, and logged out.
PostgreSQL then reported the session as `revoked`, both cookies were absent,
and an unauthenticated `/v1/me` request returned `401`.

## Remaining backend/deployment work

### Required for a hosted production email-login product

- Move the locally verified same-origin topology behind an authorized hosted
  edge and record deployment identity, image/config digests, and health receipts.
- Configure the transactional verification-delivery worker and SMTP through
  secret references. Local Mailpit delivery is development-only and is not a
  production SMTP/Vault closure.
- Add server-side protection for hosted A3 document routes. The current static
  Webapp has a client identity gate, while sensitive APIs must continue to
  enforce authorization independently on the server.
- Add production observability, abuse response, backup/restore, key rotation,
  tenant-isolation receipts, and incident recovery evidence.

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

`start-releasefoundry-demo.cmd` now:

- rebuilds the Webapp when source files are newer than exported HTML;
- starts the local server only when it is not already healthy;
- polls `/__health` before opening the page;
- writes process logs and PID metadata under ignored `.local-runtime/`;
- opens the login page at
  `http://127.0.0.1:4174/apps/webapp/out/login/`.

`scripts/install-local-demo-shortcut.ps1` creates the desktop shortcut
`ReleaseFoundry Local Demo.lnk`. After reboot, double-clicking that shortcut restores the
read-only local product demo.

`scripts/install-local-auth-shortcut.ps1` creates `ReleaseFoundry Real Login.lnk`.
After Docker Desktop is ready, this shortcut builds and starts PostgreSQL,
Mailpit, A1, Caddy, and the A3 Webapp, then opens the HTTPS login page.

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
- Local real-login verification passed for registration, Mailpit OTP delivery,
  Secure/HttpOnly cookies, `/v1/me`, refresh persistence, durable logout, cookie
  clearing, and post-logout `401`. No production email or customer identity was used.
