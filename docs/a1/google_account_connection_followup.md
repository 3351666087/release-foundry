# Google Account Connection Follow-up

Status: queued after the GitHub localhost account-connection proof. This task
does not claim that a Google OAuth client exists or that Google login is ready.

## Human Operator Inputs

- Create a dedicated Google Cloud OAuth web client.
- Configure the Google Auth Platform branding, audience, and test users.
- Register an exact localhost redirect URI.
- Store the client secret outside the repository.
- Return only the client ID suffix or digest, redirect URI, audience status,
  test-user status, and timestamp.

## A1 Implementation Gate

1. Add a Go provider adapter with exact redirect matching.
2. Require authorization-code flow, PKCE S256, state, and OIDC nonce.
3. Validate issuer, audience, subject, and verified email.
4. Keep tokens and credential values behind opaque references.
5. Enforce provider/account linking uniqueness across tenant and project.
6. Add replay, scope escalation, linking conflict, revoke, and outage tests.
7. Add Python and TypeScript client and CLI parity in the same round.
8. Persist flows, replay keys, connections, and revocation state in Postgres
   before making any production-readiness claim.
9. Capture only the redacted evidence fields allowed by the GitHub template.

## Stop Conditions

Do not request sensitive or restricted Google scopes, publish the consent
screen, add production users, or submit verification without a separate Human
Operator decision describing the exact scope and external side effect.
