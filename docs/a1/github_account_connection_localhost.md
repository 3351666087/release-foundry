# GitHub Account Connection on Localhost

Status: development-only account connection for an existing local session.
This flow is not first-time authentication, production login, or a claim that
the provider integration is commercially ready.

## Provider Registration

Use a dedicated GitHub OAuth App for localhost development.

- Homepage URL: an operator-selected public or localhost development URL.
- Authorization callback URL:
  `http://localhost:8787/oauth/github/callback`
- Minimum scopes: `read:user`; add `user:email` only when the application must
  bind a primary, verified email returned by GitHub's email endpoint.
- Keep development and production client identifiers separate.

The Human Operator generates the client secret in GitHub and writes it to the
User environment. The value must never be pasted into chat, committed, logged,
included in a command argument, or written to an evidence file.

## Secret-Safe Environment

Start a fresh PowerShell process after changing User environment variables.
Copy only the required values into the API process environment:

```powershell
$env:RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID = [Environment]::GetEnvironmentVariable(
  "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID",
  "User"
)
$env:RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET = [Environment]::GetEnvironmentVariable(
  "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET",
  "User"
)
$env:RELEASEFOUNDRY_GITHUB_OAUTH_ENABLED = "true"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_DEV_SESSION_ENABLED = "true"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_CALLBACK_URL = "http://localhost:8787/oauth/github/callback"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_DEV_TENANT_ID = "local_tenant"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_DEV_USER_ID = "local_user"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_DEV_SESSION_ID = "local_session"
$env:RELEASEFOUNDRY_GITHUB_OAUTH_FETCH_EMAILS = "true"
```

Safe metadata checks may inspect only presence, length, plausible character
shape, and whether the secret equals the client ID. Never print either value.

## Run the API

From `packages/go/releasefoundry`:

```powershell
go run ./cmd/releasefoundry-api
```

The server binds to `127.0.0.1:8787` by default. Begin the connection with:

```powershell
$response = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/projects/local_project/oauth/github/start" `
  -ContentType "application/json" `
  -Body (@{
    tenant_id = "local_tenant"
    account_id = "local_account"
  } | ConvertTo-Json)
$response.authorize_url
```

Open the returned authorization URL in the same browser session used for
GitHub. GitHub redirects to the configured callback. The callback consumes the
local state-digest transaction once. GitHub is responsible for enforcing
authorization-code single use during token exchange; the current Go runtime
does not maintain a separate local code-digest replay ledger.

The connection record and public response contain only an opaque token
reference. The current in-memory secret store still holds the raw provider
token behind that reference for the lifetime of the Go process. The raw token
must not enter logs, responses, evidence, or committed files.

Disconnect the same account connection:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8787/v1/projects/local_project/oauth/github/disconnect" `
  -ContentType "application/json" `
  -Body (@{
    tenant_id = "local_tenant"
    account_id = "local_account"
  } | ConvertTo-Json)
```

The current disconnect operation loads the process-local token, revokes it
through GitHub, then deletes the local token value and reference and marks the
in-memory connection disconnected. A provider rejection, timeout, or ambiguous
response fails closed and retains the local connection. The combined remote and
local operation is still not a durable transaction.

## Evidence Boundary

Public or committed evidence may record only:

- timestamp;
- HTTP status;
- exact callback URI;
- requested and granted scope names;
- safe account digest or short public identifier suffix;
- `token_reference_present`;
- `replay_denied`;
- disconnect status.

Do not record state, PKCE verifier, authorization code, access token, client
secret, raw provider response, request headers, cookies, or browser storage.

## Current Runtime Limits

- OAuth transactions, replay records, connections, and token references are
  process-local.
- The process-local secret store contains the raw provider token behind the
  opaque connection reference.
- Restarting the process clears transactions, replay state, token values, and
  connection state. Any callback from a pre-restart flow must be abandoned and
  replaced with a new start request.
- The SQL lifecycle migration is not yet wired into the Go runtime.
- The Go memory store does not enforce provider-subject uniqueness across
  different local accounts or projects. Do not use this localhost proof as
  evidence of account-takeover prevention or durable identity uniqueness.
- Disconnect revokes the provider token first, but remote revoke plus local
  deletion is not durable across process failure.
- The development session resolver is explicit and loopback-only.
- Production reverse-proxy normalization, secure cookies, session rotation,
  organization membership, and provider outage backoff are not implemented.
