# Google Account Connection Follow-up

Status: provider adapter and production first-login runtime are implemented;
external Google Cloud client creation and real-HTTPS operator verification are
still pending. This task does not claim that an operator-owned Google OAuth
client exists until the human operator creates it outside the repository.

## Human Operator Inputs

- Create a dedicated Google Cloud OAuth web client.
- Configure the Google Auth Platform branding, audience, and test users.
- Register the exact production HTTPS callback:
  `https://<api-host>/v1/identity/oauth/google/callback`.
- Keep `https://localhost:4443` restricted to controlled development testing
  with a separate development client.
- Store the client secret outside the repository.
- Return only the client ID suffix or digest, redirect URI, audience status,
  test-user status, and timestamp.

## A1 Implementation Gate

1. Add a Go provider adapter with exact redirect matching. **Done in A1.**
2. Require authorization-code flow, PKCE S256, state, and OIDC nonce.
   **Done in A1.**
3. Validate issuer, audience, subject, and verified email. **Done in A1.**
4. Keep tokens and credential values behind opaque references. **Done in A1.**
5. Enforce provider/account linking uniqueness across tenant and project.
   **Done in A1.**
6. Add replay, scope escalation, linking conflict, revoke, and outage tests.
   **Done in A1.**
7. Add Python and TypeScript client and CLI parity in the same round.
   **Done in A1.**
8. Persist flows, replay keys, connections, and revocation state in Postgres
   before making any production-readiness claim. **Done in A1.**
9. Capture only the redacted evidence fields allowed by the GitHub template.
   **Done in A1.**

## Stop Conditions

Do not request sensitive or restricted Google scopes, publish the consent
screen, add production users, or submit verification without a separate Human
Operator decision describing the exact scope and external side effect.
