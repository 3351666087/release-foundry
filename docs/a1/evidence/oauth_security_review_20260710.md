# A1 OAuth Security and Adversarial Review

Date: 2026-07-10

Scope:

- Reviewed and modified Python, Go, TypeScript, SQL, tests, and public A1
  evidence for the GitHub account-connection slice.
- Environment credentials were resolved only inside the controlled runtime.
  Public evidence records presence and shape checks, never credential values.
- A real existing-session localhost flow was exercised against GitHub. No raw
  provider payload, callback parameter, token, verifier, cookie, header, or
  credential value was retained in public evidence.

## Outcome

The reviewed Python control-plane and GitHub OAuth runtime now fail closed for the
P0/P1 cases in scope. Public provider/session JSON, snapshots, audit events, and
router errors omit credential references, token references, account-binding
references, raw email, email hashes, provider HTTP bodies, and unexpected
exception text.

Automated results:

```text
Focused OAuth suite: 58 passed
Full A1 suite: 714 passed, 2 skipped
TypeScript: 426 passed
Go: go test -count=1 ./... passed; go vet ./... passed
CL hygiene: passed
CL commercial: passed with 0 blockers and 0 advisories
```

## Threat Matrix

| Threat | Status | Evidence |
| --- | --- | --- |
| CSRF/state mismatch | Pass | State is length/character validated, SHA-256 bound, constant-time compared in runtime, and mismatches fail closed. |
| Callback/state replay | Pass for reviewed Python contracts; state-only for Go localhost | Python contracts retain their documented replay behavior. The Go localhost runtime consumes its local state-digest transaction once; restart clears the in-memory ledger. |
| Authorization code replay | Pass for reviewed Python contracts; provider-enforced for Go localhost | Python provider-code references are digest-bound across flows. The Go localhost runtime has no separate local code-digest ledger and relies on GitHub to reject an already-consumed authorization code. |
| PKCE downgrade | Pass | S256 is mandatory; plain/invalid verifier and method inputs are rejected. |
| Callback alias/open redirect | Pass | Exact configured redirect allowlist is required. Query, fragment, userinfo, trailing-dot host aliases, and control-plane loopback redirects are rejected. |
| Loopback development bypass | Pass for Python | Live runtime configuration requires HTTPS. Control-plane callbacks reject localhost and loopback HTTP aliases. |
| Client ID equals client secret | Pass | Equal reference strings and equal runtime-resolved values are rejected without value echo. |
| Implausible client secret shape | Pass | Secret references must identify secret, credential, or private-key material; validation messages do not include supplied values. |
| Scope escalation | Pass | Provider-returned scopes must be a subset of configured scopes before the access token is persisted. Unexpected scopes produce only `oauth_scope_escalation`. |
| Session fixation | Pass | A session ID cannot overwrite any existing session, including across tenants/projects. |
| Cross-tenant/project confusion | Pass | Flows/configs are tenant/project scoped; cross-project config ID overwrite and cross-tenant flow completion are rejected. |
| Account takeover/link conflict | Pass for reviewed Python and PostgreSQL contracts; open for Go localhost | Provider-prefixed subjects and account binding are enforced in the reviewed Python contracts, and the PostgreSQL schema has project-scoped identity uniqueness. The Go memory store does not enforce provider-subject uniqueness across local accounts or projects. |
| Unverified email | Pass for Python identity contract | Email scope requires `email_verified is True`; GitHub email-list fallback selects only primary and verified entries. |
| Secret/token/ref JSON leakage | Pass for Python | Provider config returns presence flags. Session output returns a subject digest and presence flags; account, email-hash, access-token, and refresh-token references are omitted from public JSON, snapshots, and audit. |
| Provider error/HTTP body leakage | Pass | Provider errors and unexpected router exceptions return fixed allowlisted codes/messages without HTTP body or token content. |
| Log/audit leakage | Pass for reviewed Python surfaces | No OAuth value logging was found. Tests search public results, snapshots, and audit serialization for synthetic secret/ref markers. |
| Revoked session | Pass for controlled localhost flow; durability remains partial | Go disconnect obtains the process-local token, revokes it through GitHub before local deletion, then clears the token reference and marks the connection disconnected. Provider failure retains the local connection and fails closed. Durable transaction recovery and downstream multi-instance enforcement remain open. |
| Rate limit/outage | Partial | OAuth router operations require an authenticated API key and use linked rate accounting. Provider/router failures are fail closed and redacted; distributed backoff and circuit breaking are not implemented. |

## Direct Fixes

- Hardened callback URI parsing and exact authorization redirect matching.
- Enforced state and provider-code replay protection, including stable replay
  handling after a runtime flow has completed.
- Required PKCE S256 and rejected loopback live-mode bypasses.
- Rejected equal client credential references, equal resolved values, and
  implausible client-secret reference shapes without echoing values.
- Added provider-granted scope subset enforcement.
- Parsed GitHub's comma-separated granted-scope header exactly, including
  trimming, deduplication, missing-scope rejection, and unexpected-scope
  rejection.
- Prevented cross-tenant/project flow, session, config, and subject binding.
- Prevented session ID overwrite and provider/subject mismatch.
- Removed OAuth credential, identity-binding, email-hash, and token references
  from public control-plane JSON and audit/snapshot output.
- Redacted provider response bodies and unexpected exception text.
- Minimized Go and TypeScript public connection responses to a provider-subject
  digest, login, `email_present`, connection timestamp, and non-exposure flags.
- Required the verified primary-email endpoint before reporting email presence.
- Revoked the provider token before local disconnect state is committed.

## Go and TypeScript Review

- Go and TypeScript were modified and their dedicated tests passed.
- Pass: public connection JSON never exposes the opaque token reference or raw
  provider token.
- Secret-store boundary: the Go connection stores only the opaque reference,
  but the current process-local secret store holds the raw provider token behind
  that reference until disconnect or process restart.
- Privacy: direct email is not publicly exposed. The response carries only
  `email_present`.
- Verification: when email lookup is enabled, only an entry from
  `/user/emails` that is both primary and verified can set `email_present`.
- Scope enforcement: GitHub's comma-separated scope response is parsed,
  normalized, deduplicated, and compared with the exact configured allowlist.
- Disconnect: provider-side token revocation completes before local token and
  connection deletion. A provider failure retains the local connection.
- The localhost development resolver checks explicit enablement, loopback host,
  no forwarded host, tenant identity, and revoked session status. Production
  deployment policy and proxy normalization still require environment-level
  validation by the Go owner.
- The Go transaction and connection stores are ephemeral. Restart clears state,
  replay records, raw token values, token references, and connection records;
  callbacks from pre-restart flows must be abandoned.
- The Go memory connection key includes tenant, project, session, user, and
  local account, but it does not prevent the same GitHub subject from being
  linked to another local account or project.

## Commands and Tests

```powershell
python -m pytest -q tests/a1/test_github_oauth_runtime.py tests/a1/test_oauth_security_adversarial.py tests/a1/test_oauth_account_ready.py tests/a1/test_payment_oauth_safety.py tests/a1/test_round45_provider_adapters.py tests/a1/test_oauth_postgres_lifecycle.py
```

Result: `58 passed`.

The PostgreSQL lifecycle checks in this command are static SQL contract tests,
not a live PostgreSQL or Docker proof.

The controlled real-provider proof completed:

- start succeeded;
- callback and identity lookup succeeded;
- granted scopes were exactly `read:user` and `user:email`;
- callback replay was denied with `invalid_oauth_state`;
- disconnect revoked the provider token before local deletion;
- no temporary listener or binary remained afterward.

This proves only an existing-session, memory-backed localhost account
connection. It is not GitHub login, registration, durable production OAuth, or
multi-instance account-takeover protection.

## Residual Risk

- Replay ledgers and rate counters used by these Python contracts are local
  process state. Multi-instance deployments need an atomic shared store with TTL.
- The Go localhost runtime has only a one-time state-digest transaction. It does
  not maintain a local authorization-code digest replay ledger.
- Go OAuth transactions, raw token values, opaque token references, and
  connections are process-local and disappear on restart.
- The Go memory store does not enforce provider-subject uniqueness across local
  accounts or projects; the PostgreSQL lifecycle migration is not wired into
  that runtime.
- Non-runtime control-plane completion still accepts a caller-provided
  provider-prefixed subject reference; production identity must come only from a
  verified provider response.
- Full provider issuer/audience/nonce validation is modeled for account-ready
  contracts but is not a complete GitHub OIDC implementation.
- Reconnect replacement is not yet a durable provider-revocation transaction;
  an interrupted reconnect can leave the previous provider token active.
- Disconnect performs provider-side revocation first, but the combined remote
  revoke/local delete operation is not durable or recoverable across process
  failure.
- Provider outage handling is fail closed but lacks exponential backoff,
  jitter, circuit breaking, and distributed retry budgets.
- Reverse-proxy, shared-store, multi-instance, durable replay, and production
  session hardening remain outside this localhost proof.
