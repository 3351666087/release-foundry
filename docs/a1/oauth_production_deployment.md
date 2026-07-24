# A1 Production Google/GitHub OAuth Deployment

This is the production operator checklist for the A1 first-login path. It
does not contain credentials, client secrets, authorization codes, callback
state, PKCE verifiers, nonce values, provider tokens, cookies, or mailbox
content.

## External provider setup

Create separate production web OAuth applications in the operator-owned
Google Cloud and GitHub organizations. Use the same public HTTPS API origin
that serves the Ashr runtime and register these exact callback URLs, with no
query string, fragment, trailing slash, or HTTP alternative:

```text
https://<api-host>/v1/identity/oauth/google/callback
https://<api-host>/v1/identity/oauth/github/callback
```

The Google client must be a web application OAuth client and must use the
production consent-screen/audience policy selected by the operator. The
GitHub application must be a production OAuth App with the same HTTPS callback
origin. Keep development and production client IDs separate. Do not register
`https://localhost:4443` as a production callback; that URL is reserved for
controlled development testing only.

The repository cannot create or approve resources in an operator's Google
Cloud or GitHub account. The human operator must create the applications and
place the resulting values directly into the approved secret delivery path.
Never paste a Client Secret into chat, a ticket, a shell command, a browser
field captured in evidence, or a repository file.

## Secret delivery contract

Production OAuth is enabled only when all of the following are present:

- PostgreSQL runtime and the required A1 migrations are ready.
- A mutually authenticated, external opaque vault/secret-manager bridge is
  configured with all eight `ASHR_OAUTH_VAULT_*` variables for transaction and
  provider-token material.
- A mutually authenticated, external credential resolver is configured with
  `ASHR_OAUTH_CREDENTIALS_RESOLVE_URL`,
  `ASHR_OAUTH_CREDENTIALS_MTLS_CA_FILE`,
  `ASHR_OAUTH_CREDENTIALS_MTLS_CLIENT_CERT_FILE`,
  `ASHR_OAUTH_CREDENTIALS_MTLS_CLIENT_KEY_FILE`, and
  `ASHR_OAUTH_CREDENTIALS_MTLS_SERVER_NAME`.
- Google and GitHub each receive two opaque references:
  `ASHR_GOOGLE_OAUTH_CLIENT_ID_REF`,
  `ASHR_GOOGLE_OAUTH_CLIENT_SECRET_REF`,
  `ASHR_GITHUB_OAUTH_CLIENT_ID_REF`, and
  `ASHR_GITHUB_OAUTH_CLIENT_SECRET_REF`. References must be unique and use
  an approved opaque scheme such as `vault:`, `kms:`, `secret:`,
  `provider-ref:`, or `opaque-ref:`.
- The API process must not receive
  `ASHR_GOOGLE_OAUTH_CLIENT_ID`,
  `ASHR_GOOGLE_OAUTH_CLIENT_SECRET`,
  `ASHR_GITHUB_OAUTH_CLIENT_ID`, or
  `ASHR_GITHUB_OAUTH_CLIENT_SECRET` in production. If any enabled provider
  has one of these legacy/raw variables present, startup fails closed.
- The four credential values are resolved only by the external credential
  service and are not stored in Git, `.env` files, container images, Compose
  environment literals, Terraform state, logs, documents, frontend bundles,
  or browser storage.
- The trusted server-owned organization and project IDs are configured with
  `ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID` and
  `ASHR_OAUTH_FIRST_LOGIN_PROJECT_ID`.

The API resolves credentials only on the backend through the
`OAuthCredentialsProvider` contract. Each OAuth operation resolves the
provider's two references again, so an approved reference rotation takes
effect without an API restart. The resolver request contains only the
provider, purpose `ashr.oauth.client_credentials.v1`, and opaque references;
the response is strict JSON and is never included in errors or logs. The
runtime validates presence, whitespace, control characters, size bounds,
provider/purpose binding, reference uniqueness, and Client ID/Secret
inequality without including values in startup errors. The external opaque
vault stores transaction and provider-token material by reference; PostgreSQL
stores digests and canonical account/session state, not raw OAuth secrets.

When either provider is enabled, missing credentials, missing opaque-vault
configuration, missing mTLS material, missing trusted scope, an invalid
callback, or an unavailable PostgreSQL runtime must fail startup closed.
Do not set a provider's enabled flag to `true` until its secret-manager
injection and callback registration are complete.

Example of safe *shape-only* process wiring (values are resolved by the
deployment secret manager and are intentionally not shown):

```text
ASHR_GOOGLE_OAUTH_ENABLED=true
ASHR_GITHUB_OAUTH_ENABLED=true
ASHR_GOOGLE_OAUTH_CALLBACK_URL=https://<api-host>/v1/identity/oauth/google/callback
ASHR_GITHUB_OAUTH_CALLBACK_URL=https://<api-host>/v1/identity/oauth/github/callback
ASHR_GOOGLE_OAUTH_CLIENT_ID_REF=vault:<opaque-reference>
ASHR_GOOGLE_OAUTH_CLIENT_SECRET_REF=vault:<opaque-reference>
ASHR_GITHUB_OAUTH_CLIENT_ID_REF=vault:<opaque-reference>
ASHR_GITHUB_OAUTH_CLIENT_SECRET_REF=vault:<opaque-reference>
ASHR_OAUTH_CREDENTIALS_RESOLVE_URL=https://<secret-manager-host>/v1/oauth/resolve
ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID=<server-owned-uuid>
ASHR_OAUTH_FIRST_LOGIN_PROJECT_ID=<server-owned-uuid>
```

Do not use `NEXT_PUBLIC_*` for any OAuth credential or secret reference. The
frontend receives only capability/status metadata and starts the backend
first-login route; it never receives a Client Secret, authorization code,
state, nonce, PKCE verifier, provider token, or bearer.

## Runtime and callback verification

The production `ashr-api` runtime wires Google and GitHub adapters only after
the complete dependency graph is valid:

1. resolve backend credentials;
2. construct the provider adapter and enforce exact scopes;
3. validate the absolute HTTPS callback path;
4. construct the mTLS opaque vault;
5. open and readiness-check PostgreSQL;
6. construct the migration-backed first-login store/coordinator;
7. expose browser intent, secure session/refresh-cookie, and OAuth routes.

The credential resolver must return a fresh response for each resolution.
Google and GitHub may not resolve to the same Client ID or Client Secret at
startup; this prevents a cross-provider configuration mix-up from being
advertised as ready.

The first-login callback must enforce state, nonce, PKCE S256, provider,
purpose, callback, intent, expiry, one-use transaction, and trusted
organization/project scope. Completion must atomically create or locate the
canonical account, explicitly attach the provider credential, issue the
session handoff, clear the encrypted browser intent, and return the empty
body `303` console redirect. A repeated callback, collision, provider error,
vault error, database error, revoked-session race, or scope mismatch must not
partially mutate the canonical account.

The runtime capability response is derived from the same validated flags that
construct the provider services. A disabled provider is not advertised as
first-login-capable, while an enabled provider is reported as available only
when its complete production graph is active.

## Controlled local verification

`https://localhost:4443` is for controlled development checks only. It must
use separate development provider applications and non-production accounts,
must not be used to claim production readiness, and must never be accepted by
the production runtime callback validator. Production verification takes
place on a real HTTPS test domain with operator-owned Google/GitHub test
accounts.

Record only redacted evidence: timestamp, provider name, exact callback URI,
HTTP status, safe account digest, capability status, replay denied, and
session-handoff status. Do not record provider responses, raw email addresses,
authorization codes, state/nonce/verifier values, access/refresh tokens,
Client Secrets, cookies, or browser storage.
