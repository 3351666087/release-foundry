# A3 -> A1 Identity Verification Contract Change Request

Date: 2026-07-11

Status: blocking request; A3 does not change A1 implementation in this branch.

## Observed contract

A3 calibrated against A1 commit `ac960bd` without merging the A1 draft branch.
The Go runtime currently exposes:

```text
POST /v1/identity-verification/challenges
POST /v1/identity-verification/verify
```

The challenge response deliberately contains only a uniform `accepted`
envelope. It does not return `challenge_id`, which is correct for the current
anti-enumeration policy. The development SMTP message contains the six-digit
code but does not contain `challenge_id` or another browser-safe flow token.
The verify request requires `challenge_id`, code, identifier, purpose, and
tenant scope.

This leaves a browser registration flow unable to complete: the browser never
receives the context required by `verify`.

## Required behavior

A1 should provide a mailbox-bound, short-lived verification context without
weakening these existing controls:

- The public start response remains indistinguishable for eligible, unknown,
  blocked, unavailable, and abuse-budget-exhausted requests.
- Raw email, OTP, provider subject, digest, API key, token, and cookie values do
  not enter A3 logs, analytics, fixtures, or URLs.
- The code remains single-use, expires, has an attempt cap, and is consumed in
  the same durable transaction as account or credential mutation.
- Same-email implicit account merging remains forbidden.
- A caller-supplied `account_id` remains non-authoritative.

## Recommended v2 shape

The verification email should contain a short-lived, signed, single-use link:

```text
https://<webapp>/login?mode=signup&verification_token=<opaque-mailbox-token>
```

The token must not contain a raw identifier and must not be logged. A1 should
store only a digest or use an authenticated encrypted envelope with key
rotation. The browser then submits:

```json
{
  "verification_token": "[REDACTED]",
  "code": "[REDACTED]",
  "display_name": "Example student"
}
```

A1 resolves channel, identifier, purpose, tenant, and challenge from the
server-owned token. The browser should not repeat raw identity scope fields as
proof. A second acceptable design is a Secure, HttpOnly, SameSite browser flow
cookie issued uniformly for every challenge request, including decoy flows.

After successful verification, A1 should rotate or create a secure browser
session, emit a durable identity audit event, and return a `303` redirect to an
exact allowlisted Webapp path. The callback must never expose OAuth tokens,
verification tokens, codes, raw identifiers, or provider payloads in JSON.

## Email rendering handoff

A3 provides public-safe templates:

- `apps/webapp/emails/verification-email.html`
- `apps/webapp/emails/verification-email.txt`

The HTML version uses table layout and inline CSS for transactional-email
compatibility. It has no remote image, JavaScript, tracking pixel, form,
third-party font, or user-controlled HTML. A1 must render only escaped,
allowlisted placeholders and continue to own SMTP configuration and delivery.

## A3 behavior before resolution

- OAuth and verification controls are capability-aware.
- `challenges` can be called when the A1 public configuration is present.
- `verify` is enabled only when a valid server-issued challenge context exists.
- A3 never fabricates a verified account or authenticated browser session.
- API Reference labels the incomplete verification endpoint as contract
  blocked and labels the A1 branch as draft.
