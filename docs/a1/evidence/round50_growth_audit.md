# Round 50 A1 Growth / Bus Audit

Date: 2026-07-10

## Scope And Disposition

This was an audit-only pass over the authoritative workspace
`C:/Users/33516/Documents/ReleaseFoundry_a1_clean_rebase`. No business code, shared
contract, generated fixture, peer file, secret, or callback material was
modified.

- Round49 localhost unified-account boundary: **GO**
- Current uncommitted production hardening slice: **CONDITIONAL GO**
- PR #31 merge readiness: **NO-GO**
- Production unified identity and OAuth: **NO-GO**

The uncommitted slice may proceed to an A1 closeout only after its full Go,
Python, TypeScript, fixture, and CL validation ledger is rerun. It must not be
described as production-complete.

## Authoritative Baseline

- Local branch: `agent/a1-local-sdk-runner-clean`
- Publication branch: `origin/agent/a1-local-sdk-runner`
- Audited HEAD and remote A1 head:
  `3367dc7ca0f64feeebb228d432da71a4ce639d73`
- `origin/main`: `5dbf4ee2ab4c0ea8568623899244070dce9f9ce4`
- PR #31: open, draft, blocked; 167 files, 53,424 additions, 256 deletions,
  and 7 commits
- Latest observed A2 peer:
  `78dce305 A2: track OAuth lifecycle security context`
- Latest observed A3 peer:
  `27f890c6 feat(a3): explain trust publish blockers`

No newer remote peer change conflicts with the current local A1 identity,
runtime, and revocation-outbox slice. One A2 cross-lane fixture contains an
intentional A1 route-surface refresh. Five other A2 fixture modifications are
line-ending-only noise and must remain untouched and unstaged.

The goal tool reports the commercial A1 growth goal as active. This audit also
uses `docs/strategy/large-saas-a1-a2-a3-full-plan.md`, the current user
directive, and `docs/a1/worklog.md` as operational sources of truth. The
strategy assigns A1 the identity backend, session and token lifecycle, provider
adapters, PostgreSQL/RLS, workers, and operational controls. Shared contracts
remain Gate-controlled.

## Canonical Contract Boundary

The reviewed implementation and evidence consistently use:

```text
account/principal = stable business identity
credential        = login method
membership        = tenant/project authorization
session           = authenticated session
```

GitHub, Google, WeChat, QQ, Alipay, phone, and email are credential types on
one canonical backend account. Contact equality must never implicitly merge
accounts. Credential ownership conflicts fail closed. Membership is not a
login credential and must survive link, unlink, recovery, and reviewed merge
operations.

## Verified Current Capabilities

The current uncommitted slice is materially ahead of the stale first draft of
this audit:

1. Production identity startup defaults to PostgreSQL. Memory identity requires
   development environment, explicit memory mode, and explicit enablement.
2. PostgreSQL startup requires a DSN and a session HMAC key of at least 32
   bytes, pings the database, and verifies the required 007-010 identity
   objects before serving.
3. A PostgreSQL session resolver is shared by unified identity, neutral OAuth,
   and GitHub OAuth boundaries. It queries an HMAC-SHA256 digest rather than a
   raw bearer value and accepts only active, unexpired sessions.
4. Production hosted OAuth fails closed when GitHub or Google is enabled
   without an injected external opaque vault.
5. Disconnect and reconnect supersession perform local-first durable state
   transitions and enqueue provider cleanup.
6. The revocation outbox supports `FOR UPDATE SKIP LOCKED`, expired-lease
   reclaim, lease-generation fencing, separate provider-revoked and
   vault-deleted checkpoints, retry/backoff, dead letter, and reconnect
   protection against stale cleanup.
7. Public metadata filtering is recursive and uses defensive copies. Normalized
   forbidden aliases include token-reference and revocation-outbox variants.
8. Python and TypeScript represent all seven credential providers, and the
   in-memory service protects the final login credential under concurrent
   unlink attempts.
9. The public hygiene scanner currently passes with zero findings. The prior
   claim that the unified identity evidence still failed that scan is stale.

## Production Gaps

1. Unified identity HTTP write handlers still require the concrete in-memory
   `*UnifiedIdentityService`; PostgreSQL mode passes no production write
   service. Account, credential, membership, link, unlink, and merge writes are
   therefore not a production runtime.
2. The external opaque vault/KMS is not implemented or injected. Production
   GitHub and Google OAuth are deliberately unavailable as a correct
   fail-closed consequence.
3. The revocation worker implementation exists but is not started, supervised,
   drained, or observed as a long-running production process.
4. SQLMock, static migration, and unit tests do not prove a clean-volume
   PostgreSQL migration, restricted-role RLS behavior, multi-instance races,
   restart recovery, or real outbox lease recovery.
5. Session issuance, rotation families, reuse detection, revoke-one,
   revoke-all, device inventory, and account-wide logout are incomplete.
6. Link and unlink do not enforce recent authentication or step-up. Merge has
   SDK step-up receipts, but no production reviewed-merge or recovery runtime
   exists.
7. WeChat, QQ, Alipay, phone, and email are contract/parity boundaries only.
   There is no production provider, OTP delivery, anti-enumeration, or
   real-provider calibration evidence.
8. Provider health, circuit breakers, scope drift, SLOs, OpenTelemetry,
   backup/restore, regional residency, retention, and legal-hold controls lack
   operational proof.
9. Session authentication does not yet revalidate current principal,
   credential, organization-membership, and project-membership state. Forced
   RLS also requires a narrow digest-only authentication bootstrap rather than
   a direct runtime-role table query.
10. Outbox retry does not yet reject an expired lease, malformed task contracts
    are not dead-lettered before external access, and slow provider revocation
    lacks a bounded deadline and fenced lease extension.
11. Recursive metadata key filtering is defense in depth, not a complete
    public-metadata policy. Event-specific allowlists and value-level rejection
    are still required.

## Validation And Evidence Ledger

Personally rerun in this audit:

- `python scripts/cl_guard.py hygiene`: passed, zero findings.
- Focused Python identity, Google connection, migration, and fresh-setup suite
  with repository-local `PYTHONPATH`: 90 passed in 0.74 seconds.
- Final full `tests/a1` and `tests/a2` suite with repository-local
  `PYTHONPATH`: 1038 passed and 2 skipped.
- TypeScript build and full test suite: passed, 495 tests.
- Go module tests and vet: passed.
- Go integration tests and vet: passed.
- TS/Python generated parity artifact check: passed.
- A2 fixture generator check: all 55 generated fixtures match.
- CL commercial: passed with zero blockers and zero advisories.
- `git diff --check`: passed with line-ending warnings only.
- Bounded secret and forbidden-material scan over the intended A1 publication
  set: passed with zero suspicious literal matches; no candidate value was
  printed.
- Remote refs, PR metadata/checks, working-tree status, current diffs, strategy,
  worklog, and implementation markers were inspected.

Recorded in the current worklog and treated as prior evidence:

- Fresh setup: 30/30 cases, `max_workers=4`, trace completeness `1.0`, with no
  inherited `PYTHONPATH`.

Remote checks at pushed HEAD `3367dc7c` predate the uncommitted hardening:

- Plan and hygiene: passed.
- Go SDK and integration: passed.
- TypeScript SDK parity: passed.
- Python A1/A2 contracts: failed.
- CL Gate summary: failed.

The local behavioral ledger is now green. The remote failures cannot be
considered repaired until the intended A1 commit and separately owned A2 Gate
fixture commit are integrated into the branch being checked and the new remote
CL run is green.

## Contract, Peer, And Secret Audit

- A1-owned audit path: compliant.
- Business code touched by this audit: none.
- Shared contract changed by this audit: none.
- A2/A3 semantics changed by this audit: none.
- Current cross-lane route fixture: requires explicit Gate review; it must not
  be bundled with unreviewed peer or line-ending changes.
- Secret handling: no environment values, OAuth codes, states, nonces,
  verifier data, token references, provider subjects, raw contact values,
  cookies, or headers are reproduced here.
- Production claim: prohibited until durable writes, vault injection,
  long-running workers, live PostgreSQL proofs, and green remote gates exist.

## Next 20 Growth Points

1. Replace concrete memory-service HTTP dependencies with a production
   `UnifiedIdentityStore` interface covering account, credential, membership,
   authentication, link, unlink, and audited merge operations.
2. Implement the PostgreSQL store behind that interface with tenant/project
   transaction context and fail-closed RLS.
3. Build and inject an external opaque vault/KMS adapter with versioned
   envelope encryption, rotation, binding validation, and deletion receipts.
4. Enable production GitHub and Google OAuth only through the PostgreSQL store
   and external vault, preserving the current fail-closed startup checks.
5. Start the revocation outbox worker as a supervised service with graceful
   shutdown, bounded concurrency, health endpoints, and lease-lag metrics.
6. Add clean-volume PostgreSQL migration tests for 007-010 using application
   and restricted runtime roles.
7. Add two-instance PostgreSQL race tests for provider-subject uniqueness,
   callback replay, and concurrent final-credential unlink.
8. Add restart and crash-point tests for reconnect supersession, expired lease
   reclaim, fenced completion, retry, and dead-letter recovery.
9. Implement durable session issuance and rotation families with fixation
   prevention, reuse detection, revoke-one, revoke-all, and account logout.
10. Add device/session inventory and risk signals without exposing raw bearer,
    contact, network, or provider material.
11. Enforce recent authentication and step-up receipts on link, unlink,
    recovery, merge approval, sensitive membership, and session revocation.
12. Implement explicit account recovery and human-reviewed merge workflows
    that never infer identity ownership from matching email or phone.
13. Prove membership and RBAC preservation across credential unlink, recovery,
    merge, and provider reconnection.
14. Implement WeChat, QQ, and Alipay adapters against the same principal model,
    with sandbox/live separation and private evidence handling.
15. Implement phone and email OTP credentials with anti-enumeration, replay
    resistance, delivery throttles, abuse budgets, and verified-contact state.
16. Add provider circuit breakers, health state, scope-drift detection,
    reauthorization state, and per-tenant provider rate budgets.
17. Emit redacted OpenTelemetry traces and define SLOs for callback success,
    session resolution, write latency, revocation lag, and dead-letter rate.
18. Add backup/restore and point-in-time recovery drills for identity,
    sessions, credential links, and revocation outbox state.
19. Complete Go/Python/TypeScript lifecycle and error-code parity tests for all
    seven credential providers and every public redaction alias.
20. Keep publication ownership strict: commit A1 business/evidence files to the
    A1 branch, commit the reviewed route fixture to the A2 branch, integrate it
    through Gate review, and require a fully green PR #31 before merge.

## Commands And Tests Reviewed

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
git remote -v
git branch -vv
git for-each-ref --sort=-committerdate ...
git log --left-right ...
git diff --name-status
git ls-files --others --exclude-standard
git diff --stat
gh pr list --state all
gh pr view 31 --json ...
rg -n "identity|session fixation|PKCE|RLS|OAuth|WebAuthn|MFA" docs/strategy/large-saas-a1-a2-a3-full-plan.md
rg -n "RELEASEFOUNDRY_IDENTITY_RUNTIME|FOR UPDATE SKIP LOCKED|lease_generation|revocation" packages/go/releasefoundry services/api/migrations
python scripts/cl_guard.py hygiene
$env:PYTHONPATH = (Resolve-Path packages/sdk)
python -m pytest tests/a1/test_identity_revocation_outbox_migration.py tests/a1/test_python_unified_identity.py tests/a1/test_python_google_account_connection.py tests/a1/test_fresh_setup_smoke.py -q -p no:cacheprovider
Remove-Item Env:PYTHONPATH
```

## Main-Agent Driving Instruction

Take one production identity closure slice, not another contract-only expansion:
introduce the interface-backed PostgreSQL unified-identity write path, inject an
external opaque vault, and run the revocation worker under supervision. Prove
the slice with live PostgreSQL multi-instance and restart tests, then rerun the
complete cross-language and CL ledger. Keep the A2 route fixture isolated for
Gate review and exclude all line-ending-only peer noise. Do not claim
production OAuth, production unified identity, or merge readiness before the
new remote checks are fully green.
