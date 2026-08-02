# A3 Audit Bundle Verifier / `releasefoundry gate verify --index` Money-Grade Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Money-Grade Auditor.

Theme: commercial audit for A3 audit bundle verifier and `releasefoundry gate verify --index`.

Safety boundary followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_verify_index_2026_07_07.md`.
- Did not modify code, fixtures, worklogs, acceptance checklist, or existing docs.

Evidence basis:

- A3 has Release Gate, PR Gate, Gate CLI, input artifact hashes, generated artifact manifest, waiver validation, approval validation, and a local audit bundle index with canonical `bundle_root_hash`.
- Current audit bundle index evidence still lists `releasefoundry gate verify --index`, immutable archive packaging, durable storage, GitHub artifact upload, live required check, and self-host retention backend as missing or next-step capabilities.

## Executive Verdict

The audit bundle index and root hash make A3 tamper-evident. A verifier makes A3 audit-operational.

Root hash alone is a strong fingerprint, but it is still mostly a claim unless a buyer has a simple way to recompute it, inspect every referenced artifact, and see exactly what failed. `releasefoundry gate verify --index` is the bridge from "we have a hash" to "your auditor can run this command and independently verify the release evidence package."

Money-grade read:

| Dimension | With only bundle root hash | With `releasefoundry gate verify --index` |
|---|---:|---:|
| Evidence integrity story | 7/10 | 8/10 |
| Auditor usability | 4/10 | 7/10 |
| Executive sign-off confidence | 7/10 | 8/10 |
| Self-host buyer confidence | 5/10 | 6.5/10 |
| PR/CI operational usefulness | 6.5/10 | 7.5/10 |
| Enterprise paid-pilot readiness | 7.5/10 | 8/10 |

The verifier does not by itself make A3 enterprise-complete. It does make A3 much easier to sell as audit infrastructure because the buyer can independently prove that a retained release bundle has not drifted.

## What A Verifier Can Sell

### 1. Audit-Ready Evidence Verification

Sellable promise:

> "A3 produces a release evidence bundle and gives auditors a command to verify every indexed artifact, root hash, custody event, waiver, and approval reference."

This can be sold to:

- AI governance teams.
- Security reviewers.
- Internal audit.
- Platform engineering.
- Regulated self-host teams.
- Engineering leaders who need sign-off evidence for high-risk agent releases.

Why they pay:

- They do not need to trust screenshots or manually inspect a folder.
- They can rerun verification months later.
- They can attach verification output to release approval, incident RCA, procurement evidence, or compliance review.

### 2. Enterprise Release Gate Evidence Pack

The verifier turns A3 from "release gate output" into "release gate evidence pack."

The commercial artifact becomes:

- gate JSON,
- Markdown report,
- GitHub Check payload,
- PR comment,
- generated artifact manifest,
- waiver and waiver review,
- approval and approval review,
- audit bundle index,
- root hash,
- verification result.

That is a buyer-friendly unit of value. It can sit next to SOC 2 evidence, change-management tickets, incident RCA docs, and production release approvals.

### 3. Self-Host Compliance Edition

Self-host customers care about offline proof. A verifier can run without live ReleaseFoundry, live GitHub, SaaS callbacks, or secrets.

Sellable promise:

> "You can keep A3 bundles inside your own environment and verify them locally, even during an offline audit."

This is stronger than SaaS-only dashboards because regulated teams often need local retention and independent verification.

### 4. PR Required-Check Foundation

Even before live GitHub API writes, verifier output can become a CI step:

- verify bundle index,
- fail if artifact hashes mismatch,
- fail if required artifacts are missing,
- fail if custody chain is broken,
- fail if waiver/approval references are stale,
- upload verification output as CI evidence.

This makes future branch protection more credible because the check can prove the evidence package, not just summarize the release gate.

### 5. Premium Audit Retention SKU

Verifier output creates enterprise packaging opportunities:

- audit bundle retention,
- immutable archive verification,
- dashboard audit panel,
- signed approval verification,
- replay evidence verification,
- usage and billing evidence verification,
- self-host storage verification.

This is where A3 starts to look like a paid governance product instead of a local reporting tool.

## Why Verifier Is Stronger Than Root Hash Alone

A root hash is a fingerprint. A verifier is a repeatable inspection process.

Root hash alone answers:

- "What was the claimed fingerprint of this bundle?"
- "Would the fingerprint change if the canonical index changed?"

Verifier answers:

- "Do all referenced files exist?"
- "Do their byte sizes and SHA-256 hashes match?"
- "Was the root hash recomputed from canonical index data?"
- "Was the root hash field excluded correctly from self-hashing?"
- "Are paths portable and free of local user directory leaks?"
- "Are schema versions expected?"
- "Is the chain-of-custody event hash chain intact?"
- "Do waiver and approval records referenced by the bundle match the indexed hashes?"
- "Are required evidence files missing?"
- "Is the bundle complete enough to support sign-off?"

For enterprise audit, this difference matters. A hash is evidence. A verifier is evidence plus procedure.

## Risk Reduction From `releasefoundry gate verify --index`

The verifier lowers launch risk in several concrete ways.

| Risk | How verifier reduces it |
|---|---|
| Tampered release report | Recomputes generated artifact hashes and flags mismatch. |
| Missing evidence in PR artifact | Fails when required indexed artifacts are absent. |
| Wrong bundle signed by manager | Recomputes root hash so sign-off can bind to the actual package. |
| Accidental local path leakage | Flags absolute user paths or unsafe outside-workspace references. |
| Stale waiver or approval attachment | Verifies indexed governance record hashes and expected schema versions. |
| Broken custody chain | Recomputes event hashes and `previous_event_hash` links. |
| CI artifact drift | Verifies downloaded GitHub Actions artifact against the indexed hashes. |
| Self-host retention drift | Verifies retained archive after backup, restore, migration, or legal hold. |
| Audit panic months later | Gives auditors one command and machine-readable verification result. |
| Product trust gap | Shows A3 can prove evidence integrity, not merely render a dashboard. |

The highest-value verifier behavior is fail-closed for integrity problems and explicit about what failed.

## What Still Looks Like A Toy

Even with `releasefoundry gate verify --index`, several parts remain early or toy-like unless they are hardened.

| Area | Toy-like state | Money-grade requirement |
|---|---|---|
| Immutable archive | Verifier checks an index, but there is no signed zip/tar bundle. | Package sealed archive with index, artifacts, custody log, and signature. |
| Storage | Files still live in working tree or CI artifact space. | Durable storage backend with retention, legal hold, and deletion audit. |
| Signatures | Root hash is not cryptographically signed. | Detached signature, key id, signer identity, certificate/provenance, verification status. |
| Identity | Approval is file-backed/local, not tied to GitHub/OIDC/SSO. | Authenticated signer, role authorization, separation of duties, revocation. |
| GitHub | Dry-run shapes exist, but no live required check or branch protection. | Required check policy, artifact upload, check-run id, live writer behind explicit auth. |
| Replay | Failed case ids exist, but no executable replay pack. | Replay command, input/output/trace hashes, reproduced/fixed/flaky status. |
| Dashboard | Audit bundle health is not a first-class panel. | Audit panel with root hash, verifier result, missing artifacts, custody health, retention status. |
| Billing/usage | Usage/quota is product context, not A3 metering. | Run/case/tool/media/replay/bundle storage metering and chargeback. |
| Redaction | Lightweight policy exists, but verifier may not prove DLP cleanliness. | Redaction finding log, secret scan result, fail-closed export mode. |
| Lifecycle | Bundle root hash exists, but no expiry, supersession, revocation, or deletion chain. | Full retention and custody lifecycle. |

The verifier is a serious step, but the enterprise product becomes truly durable only when it verifies sealed archives, signed approvals, storage retention, and replay evidence.

## Next Growth Points

These are money-grade next steps. They intentionally cover verifier, immutable archive, GitHub artifact upload, self-host retention, signed approvals, replay evidence, dashboard audit panel, and billing/usage.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| VER-1 | Add `releasefoundry gate verify --index <path>`. | Gives auditors a simple local command to verify bundle evidence. | Verifier |
| VER-2 | Add JSON verification output schema `a3.audit_bundle_verification.v1`. | Makes verification consumable by CI, dashboard, and self-host backend. | Verifier |
| VER-3 | Verify indexed artifact existence, byte size, SHA-256, content type, and role. | Catches tampered or missing evidence. | Verifier |
| VER-4 | Recompute canonical bundle root hash and compare to indexed root hash. | Proves the bundle index has not drifted. | Verifier |
| VER-5 | Verify chain-of-custody event hashes and previous-event links. | Detects broken or edited custody history. | Verifier |
| VER-6 | Verify required artifact policy: inputs, generated outputs, waiver, approval, custody events, redaction log, and replay pack. | Prevents partial bundles from passing as audit-ready. | Verifier |
| VER-7 | Add negative tests for tampered artifact, missing file, changed byte size, broken custody link, invalid root hash, and unsafe path. | Proves the verifier catches real audit failures. | Verifier |
| VER-8 | Add `--strict` and `--warn-only` modes. | Lets teams use the same verifier in local pilots and blocking CI. | Verifier |
| VER-9 | Add safe path validation that flags local user directories and outside-workspace paths unless explicitly redacted. | Reduces data leakage risk in exported bundles. | Verifier |
| VER-10 | Add verifier summary suitable for PR comments: passed, failed, warnings, root hash, missing artifacts. | Makes evidence status visible to reviewers. | Verifier |
| ARC-1 | Add `releasefoundry gate bundle --archive <path>` for zip/tar packaging. | Turns separate files into one customer-deliverable artifact. | Immutable archive |
| ARC-2 | Name archive using bundle id and short root hash. | Makes retained evidence easy to identify and compare. | Immutable archive |
| ARC-3 | Add archive manifest and detached signature file. | Moves from local hash to signed package. | Immutable archive |
| ARC-4 | Add write-once local archive mode that refuses overwrite. | Reduces accidental mutation after sign-off. | Immutable archive |
| ARC-5 | Add `releasefoundry gate verify --archive <path>`. | Lets auditors verify downloaded or retained bundles directly. | Immutable archive |
| GH-1 | Upload bundle index and verifier output as GitHub Actions artifacts. | Gives PR reviewers downloadable audit evidence without live GitHub API writes. | GitHub artifact upload |
| GH-2 | Upload sealed archive once archive packaging exists. | Makes CI artifact retention align with release evidence. | GitHub artifact upload |
| GH-3 | Include root hash, verifier status, and artifact name in PR comment Markdown. | Makes bundle verification legible in code review. | GitHub artifact upload |
| GH-4 | Include verifier status in GitHub Check payload summary. | Connects merge gate to evidence integrity. | GitHub artifact upload |
| GH-5 | Add artifact retention days to bundle metadata and workflow docs. | Prevents CI artifact expiry from undermining audit retention. | GitHub artifact upload |
| RET-1 | Add self-host retention policy schema with retention days, legal hold, delete-after, owner, and storage class. | Makes local evidence lifecycle auditable. | Self-host retention |
| RET-2 | Add local filesystem storage contract for retained bundles. | Enables first self-host pilots. | Self-host retention |
| RET-3 | Add SQLite/Postgres metadata design for bundles, verification runs, waivers, approvals, and custody events. | Moves from files to durable governance. | Self-host retention |
| RET-4 | Add S3-compatible object storage and WORM/object-lock option. | Supports regulated customers with existing storage controls. | Self-host retention |
| RET-5 | Add backup/restore verification workflow. | Proves retained bundles survive operational recovery. | Self-host retention |
| SA-1 | Bind approval records to `bundle_root_hash`, not only individual artifact hashes. | Makes sign-off cover the entire evidence package. | Signed approvals |
| SA-2 | Add detached approval signature over bundle root hash. | Raises non-repudiation. | Signed approvals |
| SA-3 | Add signer identity source: local attestation now, GitHub actor/OIDC/SSO later. | Turns names into auditable identities. | Signed approvals |
| SA-4 | Verifier should fail or warn on revoked, superseded, expired, or mismatched approval records. | Prevents stale sign-off from passing. | Signed approvals |
| SA-5 | Add separation-of-duties verification into bundle verification output. | Makes governance risk visible to audit. | Signed approvals |
| RP-1 | Add `a3.replay_pack.v1` with failed case ids, input hashes, trace hashes, expected output hashes, and replay command. | Turns incident replay from a list into evidence. | Replay evidence |
| RP-2 | Add replay result statuses: reproduced, fixed, regressed, new, flaky, not_replayed. | Makes release risk and remediation status auditable. | Replay evidence |
| RP-3 | Hash replay inputs and results into bundle index. | Makes RCA evidence tamper-evident. | Replay evidence |
| RP-4 | Verifier should check replay pack hashes and flag missing replay results for blocked production releases. | Reduces risk of approving unreproduced failures. | Replay evidence |
| RP-5 | Add replay-before-approval policy for high-risk waivers. | Makes exceptional approval more defensible. | Replay evidence |
| UI-1 | Add dashboard Audit Bundle panel. | Makes root hash and verifier status readable without opening JSON. | Dashboard audit panel |
| UI-2 | Show bundle completeness, hash status, custody chain status, waiver status, approval status, replay status, and retention class. | Gives managers a one-screen audit posture. | Dashboard audit panel |
| UI-3 | Add copyable verify command and root hash. | Makes handoff to auditors simple. | Dashboard audit panel |
| UI-4 | Add visual diff for failed verification: missing artifact, hash mismatch, expired approval, broken custody chain. | Turns verifier failures into actionable remediation. | Dashboard audit panel |
| UI-5 | Add print/PDF management sign-off section with verifier status. | Makes boss sign-off more defensible. | Dashboard audit panel |
| BILL-1 | Meter verification by release, bundle, artifact count, byte size, and replay count. | Creates usage foundation for enterprise pricing. | Billing/usage |
| BILL-2 | Meter stored bundle bytes and retention days. | Supports self-host or managed retention pricing. | Billing/usage |
| BILL-3 | Meter replay evidence generation and verification. | Captures cost of RCA-grade workflows. | Billing/usage |
| BILL-4 | Add team/project usage ledger for gates, bundles, verifier runs, approvals, and storage. | Enables chargeback and quota governance. | Billing/usage |
| BILL-5 | Add billing forecast in dashboard: monthly bundles, storage, verifier runs, replay workload. | Makes budget impact visible before rollout. | Billing/usage |

## Parallel Workstreams

These can move in parallel:

| Lane | First deliverable | Parallel with |
|---|---|---|
| Verifier | `releasefoundry gate verify --index` with JSON output and negative tests. | Dashboard panel, GitHub artifact docs, archive design |
| Immutable archive | Archive schema and no-overwrite local packaging. | Verifier and retention policy |
| GitHub artifact upload | Workflow step to upload index/verifier output. | PR comment/check summary updates |
| Self-host retention | Retention policy schema and filesystem storage contract. | Archive packaging and billing model |
| Signed approvals | Approval binding to bundle root hash and signature fields. | Verifier governance checks |
| Replay evidence | Replay pack schema and hash inclusion in bundle index. | Verifier required-artifact policy |
| Dashboard audit panel | Read-only panel showing root hash and verification status. | Verifier JSON output |
| Billing/usage | Usage ledger design for gates, bundles, storage, verifier runs, and replay. | Self-host retention and dashboard work |

## Commercial Positioning

Best buyer-facing message:

> "A3 gives every risky agent release a verifiable audit bundle. Your reviewer can approve a root hash, your CI can verify it, and your auditor can reproduce the evidence check later without calling ReleaseFoundry or GitHub."

What this sells now:

- Paid enterprise pilot for release evidence verification.
- Self-host audit workflow prototype.
- PR gate evidence hardening.
- Compliance review export.
- Incident RCA evidence packaging.

What it does not sell yet:

- Full immutable storage compliance.
- Cryptographic non-repudiation.
- SSO/RBAC-governed approval workflow.
- Live GitHub branch-protected required check.
- Managed retention with legal hold.
- Replay-proven remediation workflow.

## Final Auditor Call

`releasefoundry gate verify --index` is the next money-grade feature because it converts A3's root hash from a static fingerprint into an audit procedure. It gives buyers a command they can run, a result they can store, and a failure mode they can act on.

The fastest high-value sequence is:

1. Implement verifier for index, artifact hashes, root hash, and custody events.
2. Emit `a3.audit_bundle_verification.v1`.
3. Add negative tests for tampering and missing evidence.
4. Surface verifier status in PR comment, GitHub Check payload, and dashboard.
5. Upload index plus verifier output as GitHub Actions artifacts.
6. Add immutable archive packaging and `verify --archive`.
7. Bind signed approvals to bundle root hash.
8. Add replay pack verification.
9. Add self-host retention metadata and storage contract.
10. Add usage/billing ledger for bundle storage, verifier runs, and replay evidence.

The verifier is not the finish line. It is the piece that makes the rest of the enterprise story believable.

What this audit did not do:

- Did not modify code.
- Did not modify existing docs.
- Did not modify fixtures.
- Did not read or print secret-bearing files.
- Did not call ReleaseFoundry or GitHub APIs.
