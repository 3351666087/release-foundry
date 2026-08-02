# A3 Growth Auditor / Money-Grade Round 12 - 2026-07-12

> Independent request-boundary audit, remediation record, and next-round
> growth backlog. Local implementation evidence is not production validation.

## 1. Independent Verdict

**Local/contract merge candidate: GO after final full-suite and CI evidence.**

**Production hosted request boundary and Release Authority: NO-GO.**

The independent auditor initially returned NO-GO because the candidate only
handled malformed syntax. It accepted `text/plain` JSON and top-level arrays,
returned `500` for JSON `null`, had no body byte/deadline limit, and did not
persist `request_body_state`. Those high-priority local findings were fixed in
the same round before commit.

The production verdict remains NO-GO because this repository still lacks a
deployed A1 verifier, PostgreSQL with forced RLS, a browser-grade Origin/CSRF
deployment proof, a production ingress/WAF, a customer-like VPC drill, and a
durable multi-instance audit transaction.

## 2. Independent Findings and Disposition

| # | Finding | Disposition | Evidence / remaining boundary |
|---|---|---|---|
| 1 | `text/plain`, array, scalar, and `null` were not safely rejected | **Resolved locally** | Protected mutations require `application/json`; non-object JSON returns sanitized `422`. |
| 2 | Authorized body reads were unbounded | **Resolved locally** | Default 1 MiB streaming limit and 10 second total read deadline return sanitized `413/408`. Route-specific ingress limits still need production proof. |
| 3 | Audit could not distinguish unparsed, valid, or rejected body states | **Resolved locally** | `request_body_state` is included in audit evidence, payload hash, event ID seed, and persisted metadata-only event. |
| 4 | Playwright API E2E is not a true dual-Origin browser CORS test | **Open** | The E2E is now in the CI-executed A3 main spec, but it remains an API transport test under `demo_contract`. No CORS production claim is made. |
| 5 | Redacted evidence matrix is not an automatically captured receipt | **Open and honestly labeled** | The JSON is a tested redacted behavior matrix, not a production receipt. A generated probe, event IDs, commit SHA, signed bundle, and verifier remain next work. |
| 6 | Local SQLite is not production audit custody | **Open** | PostgreSQL five-level columns, forced RLS, transaction/outbox atomicity, retention, backup, restore, and multi-instance proof remain required. |

## 3. Sellable Workflow Added

This round adds a defensible **local request-boundary security control** for an
enterprise pilot:

- protected mutation identity/RBAC happens before body parsing;
- malformed, slow, oversized, wrong-media, and wrong-shape bodies receive
  stable sanitized responses;
- protected `OPTIONS` cannot bypass canonical route authorization;
- access outcomes are metadata-only and preserve A1/A2 authority boundaries;
- OpenAPI and CI-executed tests describe the same behavior.

This reduces security-review ambiguity and accidental private-data exposure.
It is not yet a standalone customer workflow or a production compliance
control. It becomes commercially stronger when connected to PostgreSQL/RLS,
SIEM, signed Audit Bundles, and customer-VPC evidence.

## 4. Capability Classification

### Implemented

- Local `400/408/413/415/422` request-boundary behavior and sanitized
  fail-closed `503` contract for authorization/audit unavailability.
- `401/403` precedence before body consumption.
- Protected route matching and metadata-only audit for `OPTIONS`.
- Request body state in access audit.
- Runtime/OpenAPI parity for all 53 protected operations.
- Focused Node integration and CI-mainline Playwright API E2E.

### Contract Supported

- A1 per-request trusted principal resolver.
- A1 production audit/data-plane sink.
- A2 trusted Decision Ledger and Release Authority resolver.
- Same-origin BFF or cross-origin gateway with explicit Origin/CSRF policy.
- A1 durable GitHub App worker and tenant repository binding.

### Production Validated

- None in Round 12.

## 5. Verification

- Focused request-boundary Node: `44 pass / 0 fail`.
- Full A3 Node: `397 pass / 0 fail`.
- CI-mainline Webapp/HTTP Playwright: `10 pass / 0 fail`.
- Full fresh-port Playwright with one worker: `35 pass / 0 fail`.
- Webapp TypeScript and Next.js production build: passed, 14 pages.
- A1 TypeScript session lifecycle: `35 pass / 0 fail`.
- A2 trusted spine: `7 pass / 0 fail`.
- Runtime/OpenAPI parity: `53/53`.
- Commercial CL: passed with 0 blockers and 0 advisories.
- Hygiene CL: passed with 0 findings.

The first parallel full Playwright run was `34/35` because an existing hover
assertion missed its transient CSS state. That test passed in isolation and
the deterministic one-worker full rerun passed all 35. No CSS was changed.

## 6. Next Round: 24 Executable Growth Points

The user-selected mainline is a real GitHub golden path plus deployment,
release, version, and new-run Audit Bundle evidence.

| ID | Vertical slice | Required state/failure coverage | Evidence and commercial value |
|---|---|---|---|
| G13-01 | Golden-path CLI: select run, A2 decision, target repo, and dry-run/live mode | missing run, invalid ledger, blocked decision, denied role, stale version | CLI receipt + tests; gives release engineers one governed entrypoint. |
| G13-02 | Golden-path API orchestration contract | A1 identity, five-level scope, idempotency, optimistic concurrency, audit failure | OpenAPI + integration tests; converts scattered APIs into a sellable workflow. |
| G13-03 | Golden-path Next.js page | loading, empty, partial, failed, denied, conflict, retry, confirmation | Playwright + screenshots; lets reviewers and owners complete the same flow visibly. |
| G13-04 | Read real tenant GitHub App installation | missing/revoked installation, wrong owner, wrong tenant | Sanitized readback; proves repository custody instead of accepting a client repo string. |
| G13-05 | Bind repository target to organization/project/environment | cross-tenant, renamed repo, archived repo, installation mismatch | Isolation tests + audit; required for enterprise GitHub governance. |
| G13-06 | Enqueue Check Run through an A1-owned worker | rate limit, retry, duplicate, revoked credential, dead letter | Worker receipt; first real external release mutation path. |
| G13-07 | Read back the created Check Run | missing external ID, status drift, conclusion mismatch, timeout | GitHub API readback fixture/receipt; distinguishes accepted request from actual delivery. |
| G13-08 | Verify required branch protection consumes the Check | check not required, bypass actor, stale SHA, branch mismatch | Branch-rule evidence; proves the gate can block a merge. |
| G13-09 | Publish and read back a PR comment | missing PR, fork restriction, edit conflict, redaction failure | Comment receipt + readback; gives developers actionable reasons. |
| G13-10 | Reviewer approve/deny/waiver state machine in golden path | assignment lock, timeout, transfer, double approval, conflict | API/UI/E2E/audit; creates a complete paid review workflow. |
| G13-11 | Preserve original A2 machine decision after human action | override hides machine result, expired waiver, scope mismatch | Decision timeline + verifier; protects compliance defensibility. |
| G13-12 | Deployment acceptance CLI | identity, DB, queue, worker, object store, A2 authority, GitHub App unavailable | Machine-readable acceptance receipt; shortens self-host handover. |
| G13-13 | Deployment acceptance page | loading/partial/failed/denied/retry and operator runbook links | Screenshot + E2E; lets administrators sign off deployment readiness. |
| G13-14 | Migration/backup/restore acceptance probes | version drift, failed migration, stale backup, restore checksum mismatch | Drill receipt; supports higher-value VPC contracts. |
| G13-15 | Versioned Release Artifact manifest | missing component, mutable digest, contract incompatibility | Manifest schema/test; makes release contents inspectable. |
| G13-16 | Git tag and GitHub Release publication plan | dirty tree, unsigned tag, duplicate version, missing CI | Dry-run then approved live receipt; establishes real version governance. |
| G13-17 | SBOM, provenance, checksums, and signature verification | tamper, missing subject, wrong key, revoked signer | Verifier output; required for supply-chain review. |
| G13-18 | Build a new run from authoritative A1 output | no trace, partial artifact, worker failure, tenant mismatch | New run receipt; ensures the bundle is not only replaying old fixtures. |
| G13-19 | Build Audit Bundle for the new run | missing A2 snapshot/decision, private payload, broken hash chain | Bundle + negative tests; joins A1 run facts to A2 authority and A3 actions. |
| G13-20 | Verify Audit Bundle independently | tamper, expired evidence, unknown schema, wrong tenant | Verifier receipt; enables security/compliance sign-off. |
| G13-21 | Hosted report from verified bundle | share/revoke/expiry/download denial and audit failure | Hosted-link E2E; creates a governed external report workflow. |
| G13-22 | GitLab parity adapter | unsupported project, token custody failure, status drift | Contract/readback tests; broadens enterprise procurement fit. |
| G13-23 | Enterprise WeChat/DingTalk/Feishu delivery | provider failure, retry, duplicate, redaction, callback verification | Sanitized delivery receipts; supports domestic enterprise operations. |
| G13-24 | Commercial release sign-off packet | missing deployment acceptance, GitHub enforcement, bundle, or owner signature | Executive report; turns technical evidence into a purchase/renewal artifact. |

## 7. Mandatory Parallel Tracks

1. **GitHub authority/readback:** G13-04 through G13-09.
2. **Deployment acceptance:** G13-12 through G13-14.
3. **Release artifact/version:** G13-15 through G13-17.
4. **New run Audit Bundle:** G13-18 through G13-21.
5. **Product workflow:** G13-01 through G13-03 and G13-10/11.

The closest path to a high-value contract is G13-04 through G13-21: a tenant
GitHub installation, real enforced check, deployment acceptance receipt,
versioned signed Release Artifact, and independently verifiable new-run Audit
Bundle.
