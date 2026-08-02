# GitHub Account Connection Recovery

Use this playbook for the localhost development flow. Every recovery attempt
must start a new authorization flow when callback completion is ambiguous.

## Configuration Rejected

Symptoms:

- missing client ID or client secret;
- client secret equals client ID;
- callback URL differs from the registered GitHub callback;
- development-session mode is disabled.

Recovery:

1. Stop the Go API process.
2. Correct User-scoped credentials without printing their values.
3. Start a fresh PowerShell process and copy the User values into that process.
4. rerun secret-safe metadata validation.
5. restart the API.

## State or Code Rejected

State mismatch, malformed state, missing code, expired state, and callback
replay fail closed. The Go runtime consumes its local state-digest transaction
once. It does not maintain a separate local authorization-code digest ledger;
GitHub is responsible for rejecting a provider code that was already consumed.
Do not retry the callback URL. Start a new flow through the project-scoped
start route with the same `tenant_id` and `account_id` used for the intended
account connection.

## Token Exchange Is Ambiguous

If GitHub times out or returns an unexpected response after the callback has
passed local state and code validation, treat the callback as consumed. This
prevents an authorization code from being retried after its remote consumption
status became unknowable. Start a new authorization flow.

## Provider Scope Escalation

If the granted scopes contain anything outside the configured allowlist, no
connection is persisted. Review the OAuth App and authorization request, reduce
the requested scopes, then begin a new flow.

## Email Is Missing

`user:email` is optional. When email binding is required, the runtime accepts
only an entry returned by GitHub's email endpoint that is both primary and
verified. A missing verified email must not be replaced with an unverified
profile field.

## Disconnect or Revoke Fails

The Go disconnect revokes the token through GitHub before deleting it from the
process-local secret store and marking the connection disconnected. It fails
closed when GitHub rejects the request, times out, or returns an ambiguous
response: the local connection is retained and the public result contains only
a redacted failure code.

The remote revoke and local delete steps are not a durable transaction. If the
process fails after provider revocation but before local deletion, treat the
connection as unresolved, restart the process, and reconnect through a new
authorization flow. Do not infer provider state from the local memory record.

## Server Restart

Current transactions, state replay records, raw token values, opaque token
references, and connection records are in memory. Restarting the Go process
clears all of them. A callback created before the restart can no longer be
completed locally; discard it and start a new flow. Do not treat restart as
provider revocation, durable logout, or a production persistence mechanism.
Reconnect the account for continued localhost testing.

## Account Connection Conflict

The current Go memory store keys a connection by local tenant, project,
session, user, and account. It does not enforce global or cross-project
uniqueness for the GitHub provider subject. A successful localhost connection
is not proof that the same GitHub identity cannot be linked to another local
account or project.

Treat any observed duplicate or conflicting link as unresolved and stop using
the affected connection. Durable provider-subject uniqueness belongs to the
PostgreSQL lifecycle contract, which is not wired into this Go runtime.
