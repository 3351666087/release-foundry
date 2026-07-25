# A1 Production Identity and Google/GitHub OAuth Deployment

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

## Password and optional recommended 2FA runtime

Password enrollment/change/recovery, TOTP enrollment/confirmation/disable,
recovery-code authentication, and recovery-code rotation are enabled only when
the API, PostgreSQL issuer/runtime, external processor, and external Vault are
all ready. Set the following API variables as one complete group:

```text
ASHR_IDENTITY_SECURITY_ENABLED=true
ASHR_IDENTITY_SECURITY_TICKET_ISSUER_DSN=<restricted-issuer-login-dsn-with-explicit-role>
ASHR_IDENTITY_SECURITY_PROCESS_URL=https://<processor-host>/v1/identity/security/process
ASHR_IDENTITY_SECURITY_CONFIRM_URL=https://<processor-host>/v1/identity/security/confirm
ASHR_IDENTITY_SECURITY_HANDOFF_CONSUME_URL=https://<processor-host>/v1/identity/security/handoff/consume
ASHR_IDENTITY_SECURITY_CLEANUP_URL=https://<processor-host>/v1/identity/security/cleanup
ASHR_IDENTITY_SECURITY_MUTATION_PREPARE_URL=https://<processor-host>/v1/identity/security/mutations/prepare
ASHR_IDENTITY_SECURITY_MUTATION_FINALIZE_URL=https://<processor-host>/v1/identity/security/mutations/finalize
ASHR_IDENTITY_SECURITY_MTLS_CA_FILE=<projected-ca-file>
ASHR_IDENTITY_SECURITY_MTLS_CLIENT_CERT_FILE=<projected-client-certificate-file>
ASHR_IDENTITY_SECURITY_MTLS_CLIENT_KEY_FILE=<projected-client-private-key-file>
ASHR_IDENTITY_SECURITY_MTLS_SERVER_NAME=<processor-server-name>
ASHR_IDENTITY_SECURITY_ORGANIZATION_ID=<server-owned-uuid>
ASHR_IDENTITY_SECURITY_PROJECT_ID=<server-owned-uuid>
ASHR_IDENTITY_SECURITY_REQUEST_TIMEOUT_SECONDS=<1-through-30>
ASHR_IDENTITY_SECURITY_TICKET_TTL_SECONDS=<1-through-300>
```

The last two timeout variables are optional and bounded; every other variable
is required when the feature is enabled. If
`ASHR_IDENTITY_SECURITY_ENABLED=false` or is absent, any residual
identity-security variable causes startup to fail closed. The issuer DSN must
be separate from the normal `a1_runtime` DSN. All six processor URLs must use
the same HTTPS origin and the exact paths shown above, with no userinfo, query,
fragment, escaped path, alternate path, or redirect.

The API-to-processor client pins the supplied CA and client identity, disables
ambient proxy discovery and redirects, and requires exactly TLS 1.3. Startup
performs a strict `GET /ready` through that mTLS channel before it opens the
issuer database. It then readiness-checks the restricted issuer role before
constructing the service and exposing the active account-security routes.
An unavailable processor, malformed readiness response, unsafe TLS profile,
invalid endpoint, shared database DSN, or failed issuer readiness prevents the
password/TOTP service from being wired into the HTTP runtime.

The API may accept a password or six-digit TOTP code only on the dedicated
authenticated mutation route. Raw password/code material is sent directly to
the trusted processor and must not be written to PostgreSQL, returned in DTOs,
placed in logs, or retained by SDK client state. TOTP remains optional and
recommended; it is never silently made mandatory by a capability flag.
Password recovery additionally requires a recent active session whose
credential is an active, login-enabled, verified email credential.

The public recovery lifecycle is exposed only through these authenticated
account routes:

```text
POST /v1/accounts/{account_id}/two-factor/recovery-codes/consume
POST /v1/accounts/{account_id}/two-factor/recovery-codes/rotate
POST /v1/accounts/{account_id}/two-factor/disable
```

Each request requires an account-bound active session, recent authentication,
same-origin CSRF/fetch-metadata enforcement, and one normalized idempotency key
bound identically in the request body and `Idempotency-Key` header. Consume
accepts one recovery code; rotate and disable accept no raw authentication
material in their JSON bodies. A recovery code is consumed at most once, and
every successful lifecycle mutation advances the account security version,
revokes affected sessions, and requires reauthentication.

## External identity-security processor and Vault

Run `ashr-identity-security-processor` as a separately deployable trusted
workload. Supply this complete processor configuration:

```text
ASHR_IDENTITY_SECURITY_PROCESSOR_LISTEN_ADDRESS=<private-host-port>
ASHR_IDENTITY_SECURITY_PROCESSOR_SERVER_CERT_FILE=<projected-server-certificate-file>
ASHR_IDENTITY_SECURITY_PROCESSOR_SERVER_KEY_FILE=<projected-server-private-key-file>
ASHR_IDENTITY_SECURITY_PROCESSOR_CLIENT_CA_FILE=<projected-api-client-ca-file>
ASHR_IDENTITY_SECURITY_VAULT_DATA_ENDPOINT_PREFIX=https://<vault-host>/v1/<kv-mount>/data/<prefix>
ASHR_IDENTITY_SECURITY_VAULT_METADATA_ENDPOINT_PREFIX=https://<vault-host>/v1/<kv-mount>/metadata/<prefix>
ASHR_IDENTITY_SECURITY_VAULT_KEYRING_ENDPOINT=https://<vault-host>/v1/<kv-mount>/data/<keyring-path>
ASHR_IDENTITY_SECURITY_VAULT_TOKEN_FILE=<projected-short-lived-token-file>
ASHR_IDENTITY_SECURITY_VAULT_CA_FILE=<projected-vault-ca-file>
ASHR_IDENTITY_SECURITY_VAULT_CLIENT_CERT_FILE=<projected-vault-client-certificate-file>
ASHR_IDENTITY_SECURITY_VAULT_CLIENT_KEY_FILE=<projected-vault-client-private-key-file>
ASHR_IDENTITY_SECURITY_VAULT_SERVER_NAME=<vault-server-name>
ASHR_IDENTITY_SECURITY_VAULT_NAMESPACE=<optional-vault-namespace>
ASHR_IDENTITY_SECURITY_TOTP_ISSUER=<optional-display-issuer>
ASHR_IDENTITY_SECURITY_VAULT_TIMEOUT_SECONDS=<1-through-30>
ASHR_IDENTITY_SECURITY_READINESS_TIMEOUT_SECONDS=<1-through-30>
ASHR_IDENTITY_SECURITY_SHUTDOWN_TIMEOUT_SECONDS=<1-through-120>
```

`ASHR_IDENTITY_SECURITY_VAULT_TOKEN` is explicitly forbidden. Deliver a
short-lived token only through
`ASHR_IDENTITY_SECURITY_VAULT_TOKEN_FILE`; a Vault Agent, workload-identity
sidecar, or equivalent production Secret Manager integration must refresh the
projected file before expiry. The processor reads the file for each Vault
operation so token rotation does not require a processor restart. Do not put a
token, key, DSN, password, OAuth Client Secret, or credential reference into a
frontend variable, `NEXT_PUBLIC_*`, repository file, document, browser
storage, container image, command transcript, or log.

The processor listener requires and verifies an API client certificate and
allows exactly TLS 1.3. The processor-to-Vault client likewise pins the Vault
CA/server name, presents its workload certificate, requires exactly TLS 1.3,
refuses redirects, and applies bounded timeouts. Startup resolves the Vault
KV-v2 key ring and verifies data-plane readiness before serving traffic.
`/health`, `/ready`, process, confirm, mutation prepare/finalize, one-use
handoff, and cleanup responses all carry `Cache-Control: no-store`.

The Vault key-ring record contains one active version and may retain previous
versions during a controlled rotation. New records always use the active key.
Existing records remain usable only while their referenced previous key is
still present; retiring that key makes those records fail closed. Rotation
therefore proceeds as:

1. add the new key while retaining the previous key;
2. mark the new version active and verify readiness;
3. allow in-flight records/handoffs to complete or clean them up;
4. use aggregate-only evidence to verify no retained record needs the previous
   version; and
5. remove the previous key and re-run readiness/failure tests.

The processor uses Vault KV-v2 compare-and-swap operations for idempotency,
replica concurrency, and one-use claims. TOTP provisioning URIs and recovery
codes are returned through separate handoff identifiers and exactly one
consumer may win. Recovery codes are returned once, then removed from the
stored record. Cleanup tokens compensate failed or partial API/database
mutations without exposing the stored secret. A Vault outage, timeout,
read-only response, CAS conflict, malformed key ring, retired key, handoff
replay, or cleanup mismatch must return a stable redacted error and leave no
new active account-security state.

## PostgreSQL migration 028 issuer and RLS boundary

Apply `028_a1_scoped_identity_security_ticket_issuer.sql` before enabling the
password/TOTP runtime. Migration 028 adds forced-RLS issuance records and only
these issuer entrypoints:

```text
a1_issue_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
)
a1_cancel_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
)
```

Create `a1_security_ticket_issuer` as an independent `NOLOGIN`,
`NOSUPERUSER`, `NOBYPASSRLS`, `NOINHERIT` role. Create a separate restricted
`LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOINHERIT` deployment principal,
grant it membership in the issuer role, and make its dedicated DSN explicitly
select `a1_security_ticket_issuer` (for example through the PostgreSQL startup
`role` option). The API must never reuse the normal runtime pool for this
connection.

The `a1_runtime` role receives no issuer function authority. The issuer role
receives no direct sensitive-table privilege, no schema-create privilege, no
general ticket resolution/execution authority, and no account-security
projection authority. It may execute only the two scoped issue/cancel
functions. Those `SECURITY DEFINER` functions retain the exact
`pg_catalog, public, pg_temp` search path, enforce organization/project,
canonical principal/actor, recent session, idempotency, context digest, ticket
TTL, and forced-RLS scope, and reject password recovery unless the recent
session is backed by a verified active email credential.

Startup readiness verifies that `current_user` is the `NOLOGIN` issuer role,
`session_user` is a separate restricted `LOGIN` member, both roles are
`NOSUPERUSER`, `NOBYPASSRLS`, and `NOINHERIT`, the issuance table has enabled
and forced RLS, only the scoped functions are executable, and the issuer has
no direct access to issuance, receipt, or mutation-ticket tables. Deployment
verification must also check function ownership, ACLs, and the fixed search
path. Never repair readiness by granting the issuer or runtime direct table
access.

## PostgreSQL migration 029 recovery lifecycle and RLS boundary

Apply `029_a1_totp_recovery_lifecycle.sql` after migration 028 and before
enabling the recovery-code consume/rotate or TOTP-disable routes. Migration 029
extends the restricted issuer and runtime contracts with exactly these
operations:

```text
mfa_recovery_consume
mfa_recovery_rotate
mfa_disable
```

The issuer must bind every ticket to the canonical account, actor, active
session, organization, project, operation, request digest, idempotency key,
recent-authentication window, expected security version, and expected
processor-state digest/count. The normal runtime role may execute only the
scoped mutation and private projection functions required by the service; the
issuer, `PUBLIC`, and browser-facing callers receive no direct access to the
five sensitive lifecycle tables. Enabled and forced RLS, `_self` policies,
fixed `SECURITY DEFINER` search paths, restricted function ACLs, and distinct
`LOGIN`/`NOLOGIN` role identities are production startup requirements rather
than optional hardening.

The transaction order is fail closed:

1. the trusted processor prepares the account-bound secret mutation and
   returns only backend mutation material;
2. the restricted issuer creates the scoped ticket;
3. PostgreSQL atomically applies the mutation, idempotency record,
   `security_version` increment, session revocation, audit event, and
   `identity_outbox` event;
4. the processor finalizes the prepared Vault state; and
5. if ticket issuance, PostgreSQL validation, or the database mutation fails,
   the API invokes processor cleanup compensation and returns a stable
   redacted error.

For recovery rotation, the new 6-20 code batch is released only through the
processor's one-use handoff with `Cache-Control: no-store`; exactly one
consumer may obtain it. Raw TOTP secrets, TOTP codes, and recovery codes must
never enter PostgreSQL, logs, audit/outbox payloads, or replay records. Opaque
secret references, digests, mutation tickets, cleanup/finalize tokens, and
processor replay material may exist only inside their private forced-RLS
backend projections and must never appear in PostgreSQL public results,
browser-safe DTOs, frontend state, logs, or SDK-retained state. Public
consume/disable responses never contain recovery codes; only a successful
rotation response may contain the one-use code batch.

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
