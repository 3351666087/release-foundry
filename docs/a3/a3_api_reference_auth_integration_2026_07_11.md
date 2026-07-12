# A3 API Reference and Auth Integration

Date: 2026-07-11

> Follow-up correction: A1 `c784163` confirms that the current Google and
> GitHub routes are credential-linking routes for an already authenticated
> account, not initial sign-in. A3 now keeps those login buttons disabled. See
> `docs/a3/a3_upstream_identity_trusted_spine_alignment_2026_07_11.md`.
>
> Merged-main update, 2026-07-12: A1 `c784163` and A2 `8cd1d4f` entered
> `main` through `7dd14d7`; current `main` is `ccf6ce5`. Their implemented
> route and trusted-spine contracts are authoritative; initial OAuth login and
> browser email-completion blockers remain unchanged.

## Scope

This round adds the developer reference and the first real A3-to-A1 identity
adapter. It follows `docs/strategy/large-saas-a1-a2-a3-full-plan.md`:

- TypeScript and Next.js remain the A3 product-web mainline.
- Ashr official API is an optional calibration provider, not a runtime or CI
  dependency for this A1/A2/A3 product path.
- A1 owns identity sessions, OAuth exchanges, credentials, SMTP, and execution
  facts.
- A2 owns score, pass/fail, failure taxonomy, and release decisions.
- A3 owns product presentation and fails closed when upstream authority is not
  available.

## Upstream calibration

The initial pass used read-only peer refs. The current calibration now uses
the integrated `main` snapshot:

| Lane | Ref | SHA | Use in this round |
|---|---|---|---|
| main | `origin/main` | `ccf6ce5` | current provider-neutral enterprise Release base |
| A1 | `main` source commit | `c784163` | OAuth account linking, unified identity, verification, SMTP, route facts |
| A2 | `main` source commit | `8cd1d4f` | five-level trusted evidence scope and unchanged judge authority |

A3 did not modify A1 or A2 semantics. The API Reference marks merged route
implementation separately from product readiness: account linking, challenge
start, and session refresh are implemented; initial provider sign-in and
browser verification completion remain unavailable or blocked.

## Product changes

### API Reference

The Next.js Webapp now has `/api-reference` with:

- Chinese-first and English copy.
- Search by method, path, owner, or title.
- Identity/OAuth, run/evidence, judge/release, and console/report filters.
- A1/A2/A3 owner labels.
- Implemented, local-draft, and contract-blocked state.
- Public-safe request and response examples.
- Authentication boundary, source file, source commit, and safety notes.
- Desktop and mobile layouts.

### Google and GitHub account linking

`apps/webapp/lib/auth-api.ts` exposes an account-linking adapter for the A1
project-scoped start routes. It uses the existing trusted session and no
caller-supplied account ID. A3 validates the returned authorization URL
against the exact official provider host before a future account-settings
surface may redirect:

- Google: `accounts.google.com`
- GitHub: `github.com`

The browser never receives provider secrets. These routes are not wired into
the login page. The current A1 callback returns a JSON connection object, so
initial hosted OAuth sign-in, session creation, and an allowlisted redirect
remain explicit backend blockers.

### Email registration

The registration form collects display name, email, and explicit consent in
component state only. It does not persist them to localStorage. A configured
build can call the real A1 challenge endpoint. The UI preserves A1's uniform
anti-enumeration response and does not claim that a message was definitely
delivered.

Verification remains fail-closed until A1 supplies browser-safe challenge
context. See
`docs/a3/a1_identity_verification_contract_change_request_2026_07_11.md`.

### Email design

A3 adds a responsive in-product preview plus HTML and plain-text handoff
templates. The template is intentionally transactional rather than marketing
styled. It uses no scripts, tracking, remote assets, or secret values.

## Public build configuration

The browser accepts only these non-secret variables:

```text
NEXT_PUBLIC_A1_API_BASE_URL
NEXT_PUBLIC_A1_PROJECT_ID
NEXT_PUBLIC_A1_TENANT_ID
```

`apps/webapp/auth.env.example` documents local values. OAuth client secrets,
SMTP credentials, API keys, callback codes, tokens, and cookies must never use
`NEXT_PUBLIC_` variables and remain A1-owned.

## Security disposition

- HTTPS is required for non-loopback API bases.
- API base URLs containing user info, query, or fragments are rejected.
- OAuth authorization URLs are exact-host allowlisted.
- Requests use 12-second timeouts and sanitized public errors.
- No secret or personal data is logged by the A3 client.
- No real OAuth, email, or account mutation was executed during automated
  development.
- The read-only demo remains available and explicitly does not create an
  account.
