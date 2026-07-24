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

### PostgreSQL migration 027 runtime boundary

Apply migrations through
`027_a1_oauth_first_login_runtime_create.sql` before enabling either
first-login provider. Migration 027 adds the only runtime-authorized creation
entrypoint for the sensitive OAuth transaction table:

```text
a1_create_oauth_runtime_transaction(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
)
```

The production runtime role must be `NOSUPERUSER`, `NOBYPASSRLS`, and
`NOINHERIT`. It receives `EXECUTE` on this function but no direct table or
column privilege on `oauth_runtime_transactions`. `PUBLIC` must not have
function, table, or column access. The transaction table must have both
enabled and forced RLS. The function must remain `SECURITY DEFINER`, owned by
a non-runtime role that the runtime cannot inherit, and must keep the exact
`pg_catalog, public, pg_temp` search path. Production readiness checks all of
these properties and fails startup if any property changes.

Do not work around a readiness failure by granting direct
`INSERT`/`SELECT`/`UPDATE`/`DELETE` access to the runtime. Repair the migration,
function ACL, owner, role attributes, or RLS configuration instead.

### Browser start navigation boundary

The public provider start route accepts either:

- a request with exactly one valid same-origin HTTPS `Origin`; or
- a normal same-origin top-level document navigation that omits `Origin` but
  supplies exact `Sec-Fetch-Site: same-origin`,
  `Sec-Fetch-Mode: navigate`, `Sec-Fetch-Dest: document`, and a same-host
  HTTPS `Referer`.

The route rejects forwarded-host/client identity headers, cross-site fetch
metadata, missing or duplicate required values, non-document requests, and
malformed referrers. This navigation exception applies only to the public
OAuth start route and its browser-intent issue step; it does not weaken email
verification, explicit credential binding, or any other mutation route.

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

For each provider, the real-HTTPS release gate must prove:

1. the backend capability advertises first login only while the complete
   provider/runtime graph is ready;
2. the provider authorization request contains `state`, `nonce`,
   `code_challenge`, and `code_challenge_method` without recording any value;
3. the callback reaches the exact registered HTTPS URI and completes with an
   empty-body `303 /console` handoff;
4. the access and refresh cookies are issued with the production security
   attributes while their values remain uninspected and unrecorded;
5. one canonical account and one active provider credential exist in the
   trusted tenant/project scope, using count/provider-set evidence only;
6. the corresponding runtime transaction is consumed or cleared and no raw
   provider material is present in PostgreSQL;
7. replay is rejected and provider/Vault/database failures leave no partial
   account, credential, session, or token-reference mutation.

Google and GitHub must each pass this checklist independently. A successful
Google flow is not evidence for GitHub, and a provider-console configuration
screen is not evidence that the callback/session handoff works.

## Controlled real-HTTPS release evidence (2026-07-24)

The release exercise used the operator-controlled temporary HTTPS host
`depending-while-munich-dare.trycloudflare.com`. This hostname is evidence for
the dated controlled test only; it is not a permanent production endpoint and
must not be copied into production configuration. The registered callback
paths were:

```text
/v1/identity/oauth/google/callback
/v1/identity/oauth/github/callback
```

Both provider applications were created or verified through the operator's
Chrome Extension session. Their Client ID/Client Secret pairs were delivered
to the backend as four opaque mTLS external-Vault references. The API
container had no raw Google/GitHub OAuth credential environment variable and
no `NEXT_PUBLIC_*` credential or secret. The provider start buttons were
enabled from the validated runtime capability rather than a frontend
hard-code.

Google and GitHub independently completed the safe HTTP sequence:

```text
302 GET /v1/identity/oauth/<provider>/start
303 GET /v1/identity/oauth/<provider>/callback
200 GET /console
```

The Google round trip proved one-use state consumption, PKCE exchange,
nonce/OIDC identity validation, canonical account creation, explicit Google
credential attachment, access/refresh session-cookie handoff, and the external
Vault transaction put/get/binding/delete lifecycle. The GitHub round trip
proved the corresponding one-use state, PKCE, canonical-account,
explicit-credential, session-handoff, and Vault lifecycle; GitHub's OAuth
identity response is not treated as a Google-style OIDC ID-token nonce flow.
No query value, provider subject, email address, account/credential/session ID,
cookie, token, opaque reference, or digest was recorded.

After both first logins, count/provider-set evidence was:

```text
principals=2
active_credentials=2
credential_providers=github:1,google:1
active_sessions_with_refresh=2
completed_first_login=2
completed_created=2
active_opaque_refs=2
active_opaque_providers=github:1,google:1
```

The two independently authorized provider identities therefore remained
separate canonical principals; the runtime did not infer an unsafe
cross-provider merge. Explicit credential binding remains a separate
authenticated operation.

A second Extension login for each provider completed the same
`302`/`303`/`200` handoff. Final aggregate evidence was:

```text
principals=2
active_credentials=2
credential_providers=github:1,google:1
active_sessions_with_refresh=4
completed_first_login=4
account_created=2
account_reused=2
operation_providers=github:2,google:2
active_opaque_refs=2
revocation_pending_refs=2
pending_revocations=2
```

This proves known-subject login reuses the canonical account and credential,
creates a fresh session, keeps only the current provider token reference
active, and sends replaced references to the controlled revocation outbox.

Real provider callbacks are not replayed because doing so would require
capturing secret-bearing callback queries. Replay and failure atomicity are
instead release-gated by deterministic HTTP and restricted-role PostgreSQL
tests: callback replay returns `400` before canonical mutation or secret
storage; exact transaction replay returns one canonical relation;
verified-email conflict rolls back all mutations; and transaction,
provider/Vault, database, trusted-scope, and RLS failures return no receipt or
partial canonical state.
