# A1 Round 60 - Canonical Identity, OAuth, and SDK Client Parity

Date: 2026-07-14

## Scope

This round advances the commercial identity boundary shared by the Go control
plane and the Python/TypeScript SDKs:

- registration and login are separate operations and routes;
- one canonical account may own multiple explicitly bound credentials;
- credential binding requires an authenticated session, an opaque
  account-bound proof, and explicit user consent;
- email-first defaults are suitable for domestic users;
- MFA is optional but can be recommended and challenged through a typed
  response;
- QQ and WeChat remain typed OAuth capabilities;
- OAuth login and OAuth linking remain distinct, with linking unable to
  silently merge accounts by matching email;
- all A3-facing client objects serialize without session tokens, binding
  proofs, authorization URLs, raw OAuth state, or provider credentials.

No real credential, OAuth token, authorization code, customer email, provider
subject, or private payload is included in this evidence.

## Go identity authority

Implemented surfaces:

- `packages/go/ashrclone/identity.go`
- `packages/go/ashrclone/identity_http.go`
- `packages/go/ashrclone/identity_oauth.go`
- `packages/go/ashrclone/server.go`

The Go authority now provides:

- separate email registration and email login challenges;
- canonical account creation and account-bound sessions;
- explicit multi-credential binding without generic merge/link behavior;
- typed MFA requirements and completion;
- QQ/WeChat OAuth capability metadata;
- PKCE S256, one-time HMAC state, exact redirect allowlists, and fail-closed
  coordinator/server authority matching;
- key identifiers for HMAC material, rotation support, and retirement checks
  that refuse to retire a key while live records still reference it;
- public-safe HTTP response writers with no-store headers;
- rejection of registration-only metadata on login/link completion paths.

The public Go route manifest now includes:

- `POST /v1/identity/registration/email/begin`
- `POST /v1/identity/registration/email/complete`
- `POST /v1/identity/login/email/begin`
- `POST /v1/identity/login/email/complete`
- `POST /v1/identity/oauth/begin`
- `POST /v1/identity/oauth/complete`
- `POST /v1/identity/mfa/complete`
- `POST /v1/identity/credentials/bind`
- `POST /v1/identity/sessions/revoke`
- `GET /v1/me`

`docs/a1/evidence/go_python_ts_route_parity_snapshot.json` was refreshed from
the current source. These identity routes remain intentionally Go-only in that
SaaS route snapshot because Python and TypeScript consume them through the
separate identity clients rather than the existing SaaS/OpenAPI client
surface.

## Python and TypeScript clients

Python:

- `packages/sdk/ashr_clone/identity_client.py`
- `tests/a1/test_identity_client.py`

TypeScript:

- `packages/ts/ashr-clone/src/identity-client.ts`
- `packages/ts/ashr-clone/test/identity-client.test.mjs`

Both clients expose equivalent operations for registration, login, MFA, OAuth,
binding, current-account lookup, session revocation, and deriving a client
with a session. Both fail closed on unsupported response schema versions.

Security behavior verified in both languages:

- link-mode OAuth requires an authenticated session;
- binding requires explicit consent;
- outbound authorization/session/binding secret material is usable by the
  transport but absent from public serialization and safe representations;
- errors are sanitized;
- no generic merge API is exported.

The generated parity matrix now checks 11 identity method pairs, 10 identity
routes, registration/login separation, explicit binding consent, safe
serialization of session tokens/binding proofs/OAuth URLs, fail-closed schema
handling, and typed domestic OAuth capability surfaces.

## PostgreSQL and RLS status

The migration and embedded Go schema now declare:

- canonical `ashr_accounts`;
- hashed/fingerprinted `ashr_identity_credentials`;
- encrypted delivery-target plus keyed-hash `ashr_identity_challenges`;
- keyed-hash `ashr_identity_sessions`;
- account-to-tenant organization memberships;
- account-context RLS for account and membership reads;
- forced RLS and deny-by-default end-user access for credential, challenge, and
  session rows.

The schema is key-identifier/rotation ready and forbids plaintext OAuth access
tokens, refresh tokens, session tokens, and challenge secrets. Static migration
tests pass.

Current limitation: the Go identity authority is still an in-memory runtime;
repository methods that durably read/write these identity records and perform
transactional key rotation have not yet been wired to PostgreSQL. Delivery
target encryption/key rotation is represented in the schema but is not yet a
complete production persistence path.

The live migration/RLS test is gated by `A1_POSTGRES_TEST_DSN`. It was skipped
in this environment because that variable was not configured, so this round
does not claim a live PostgreSQL/RLS pass.

## Validation

- `python -m pytest -q tests/a1/test_identity_client.py`
  - `4 passed`
- `python -m pytest -q tests/a1/test_ts_python_gap_matrix.py tests/a1/test_identity_client.py`
  - `5 passed`
- `python -B tests/a1/ts_python_parity_matrix.py --check`
  - passed
- `python -m pytest -q tests/a1/test_go_python_route_contract_evidence.py`
  - `8 passed`
- `python -m pytest -q tests/a1`
  - `343 passed`, `1 skipped`
- `npm test` in `packages/ts/ashr-clone`
  - `333 passed`, `0 failed`, `0 skipped`, `0 todo`
- `go test ./...` in `packages/go/ashrclone`
  - passed
- `python -m pytest -q tests/integration/test_a1_control_plane_identity_migration_live.py`
  - `1 skipped` because `A1_POSTGRES_TEST_DSN` was not configured
- `git diff --check`
  - passed; Git emitted line-ending conversion warnings only
- `go test -race ./...`
  - not runnable in the current Windows toolchain: the default environment has
    CGO disabled, and with `CGO_ENABLED=1` the build fails because `gcc` is not
    installed or present on `PATH`

## Remaining blockers

1. Implement a PostgreSQL-backed identity repository and wire the Go authority
   to transactional account, credential, challenge, session, and membership
   persistence.
2. Implement production delivery-target encryption and key-provider-backed
   rotation, including live-record retirement/migration tests.
3. Run the live migration twice and RLS isolation probe against a configured
   PostgreSQL test database.
4. Add PostgreSQL concurrency tests proving one-time challenge/session/binding
   consumption and canonical credential uniqueness under races.
5. Install a supported C toolchain and run the Go race suite.
6. Add end-to-end Python and TypeScript identity client smoke tests against the
   compiled Go HTTP server.
7. Add production OAuth adapter integrations for QQ and WeChat without
   weakening exact redirect, PKCE, state, explicit-link, or redaction rules.

Overall A1 remains in progress.
