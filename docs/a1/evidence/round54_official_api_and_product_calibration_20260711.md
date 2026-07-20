# Round 54 Official API And Product Calibration

Date: 2026-07-11

## Control Boundary

- The official credential was read only from the process environment. Its
  value was never printed, passed as a command argument, or written to a
  tracked file.
- In-app Browser was attempted first and Chrome second. Both controllers
  failed while initializing local control assets, before navigation. The
  static frontend mirror was therefore used as the agreed read-only fallback.
- Static string presence is not treated as live product behavior or an
  official API contract.

## Dry Run And Read-Only Small Batch

The Python calibrator dry run planned five read operations and seven estimated
calls. The real zero-retry small batch then completed all five operations with
HTTP 200: init, health-check, list-agents, list-datasets, and list-requests.

Four additional operations were each planned before execution and completed
with one HTTP 200 attempt: list-runs, get-request, get-dataset, and get-run.
The public summaries contain response field names and bounded collection
counts only. Raw objects and identifiers remain in ignored private evidence.

Tracked summaries:

- `docs/a1/evidence/official_api_round54_readonly_public_summary.json`
- `docs/a1/evidence/official_api_round54_extended_readonly_public_summary.json`

## Mutation Gate

The prior Round 53 text control reached the official API but was quota-blocked
inside an HTTP 200 envelope. Round 54 read-only responses expose neither a
quota/reset header nor another reviewed signal that capacity changed. A fresh
request-bound plan therefore returned `blocked`. No text or paid-media
mutation was submitted, and no generation or charge is claimed.

This is deliberate fail-closed behavior: user authorization permits paid
calibration, but it does not make repeated calls under unchanged quota evidence
useful evidence.

## Mirror Findings

The archive still contains 589 entries, including 197 bounded text-like
entries. It contains `refresh_token`, `session_id`, tool-call, API-key, and
media strings, but no exact `verification_token`, `challenge_id`,
`browser-sessions/refresh`, `evidence_snapshot`, or `decision_ledger` marker.
These counts neither prove nor disprove a server capability.

Tracked public-safe map:

- `docs/a1/evidence/frontend_mirror_round54_identity_evidence_map_20260711.json`

## Private Evidence

The dry-run plans, real response records, and quota plan gate are under
git-ignored `docs/evidence/private_refs/`. Public artifacts name those paths
for provenance but do not copy raw payloads, IDs, header values, quota counts,
or credentials.

## Registration, Login, And Account Linking Calibration

Official Google and GitHub documentation was reviewed again on 2026-07-12.
The product contract deliberately separates four operations:

1. Registration establishes a new canonical account only after the chosen
   initial credential is verified. Domestic email is the preferred available
   path. OAuth-first registration may copy only a provider-verified email and
   creates no local password.
2. Login proves one exact credential already attached to one existing account.
   It cannot create an account, attach a credential, infer ownership from an
   email match, or merge accounts.
3. Credential linking is an authenticated settings operation. It requires a
   fresh account session, explicit user intent, provider proof, subject
   uniqueness checks, CSRF/state protection, audit history, and a safe cancel
   or unlink path.
4. Password enrollment, recovery methods, passkeys, and 2FA are post-
   registration security operations. Password remains optional for OAuth-first
   accounts, while 2FA is optional and recommended.

This follows the mainstream distinction between account creation,
authentication, OAuth consent, and account linking while applying a stricter
anti-takeover rule: a matching email address is never sufficient to auto-link
or auto-merge canonical accounts.

Provider capability entries remain first-class for email, Google, GitHub,
WeChat, QQ, Alipay, and phone. Providers requiring unavailable business
qualification or production configuration report an explicit unavailable
reason and fail closed; their presence in the contract is not a claim that
production login is currently enabled.

The A3 projection is intentionally public-safe. It may expose canonical
account ID, primary-email presence/verification/source, password status, 2FA
status and recommendation, safe credential descriptors, memberships, and
provider readiness. It must not expose raw or digested email, provider subject
or subject digest, secret references or fingerprints, lifecycle receipt IDs or
digests, encrypted proof material, or provider tokens.
