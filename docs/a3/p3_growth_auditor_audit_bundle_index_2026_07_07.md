# A3 Audit Bundle Index / Root Hash / Chain-of-Custody Growth Audit - 2026-07-07

## Audit Scope

Role: A3 Growth-Auditor / Audit Bundle Auditor.

Focus: audit bundle index, bundle root hash, chain-of-custody events, immutable retention, verification command, GitHub artifact upload, self-host storage, and replay evidence.

Safety boundary followed:

- Read local repo evidence only.
- Did not read or print `.env.local`, API keys, cookies, tokens, or live signed media URLs.
- Did not call the live Ashr API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_audit_bundle_index_2026_07_07.md`.
- Did not modify Gate CLI, Gate CLI tests, P3 fixtures, worklogs, or acceptance checklist files owned by the main agent.

Evidence reviewed:

- `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- `docs/a3/p3_gate_cli_growth_2026_07_07.md`
- `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`
- `docs/a3/p3_waiver_validation_growth_2026_07_07.md`
- `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md`
- `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`
- `docs/a3/p3_growth_auditor_waiver_workflow_2026_07_07.md`
- `docs/a3/p3_growth_auditor_signed_approval_2026_07_07.md`

## Executive Verdict

A3 has crossed an important local governance threshold. It now has:

- Release Gate and PR Gate evidence.
- Gate CLI JSON and Markdown outputs.
- SHA-256 hashes for input artifacts.
- Generated artifact manifest for JSON report, Markdown report, GitHub Check payload, and PR comment Markdown.
- File-backed waiver validation with expiry, scope, required approver roles, failed-check coverage, and reviewed artifact hashes.
- File-backed approval validation with decision binding, waiver binding, required signer roles, reviewed artifact hashes, and separation-of-duties guardrail.

The next missing commercial layer is an audit bundle index with a canonical root hash. Today A3 can prove many individual pieces. It cannot yet prove that all reviewed pieces were assembled into one sealed, immutable, retained, replay-verifiable release evidence package.

Narrow maturity read:

| Dimension | Current read | Auditor note |
|---|---:|---|
| Input artifact integrity | 8/10 | Gate CLI hashes source evidence files in the audit manifest. |
| Generated artifact integrity | 7/10 | Generated JSON, Markdown, GitHub Check, and PR comment artifacts are hashed. PDF, screenshots, replay packs, redaction logs, waiver, and approval package links still need bundle-level treatment. |
| Waiver validation | 7/10 | Local `a3.waiver.v1` and `a3.waiver_review.v1` make exceptions structured and time-bound. |
| Approval validation | 6.5/10 | Local `a3.approval.v1` and `a3.approval_review.v1` create sign-off evidence, but not cryptographic identity or durable persistence. |
| Bundle index | 2.5/10 | Audit bundle is named conceptually, but there is no first-class index tying every artifact together. |
| Bundle root hash | 1.5/10 | No canonical root hash over inputs, generated artifacts, waiver, approval, custody events, replay pack, and retention metadata. |
| Chain of custody | 2/10 | Creation and validation outcomes exist, but no append-only event ledger. |
| Immutable retention | 2/10 | No WORM/object-lock/local immutable archive policy or retention lifecycle. |
| Verification UX | 2/10 | No `ashr gate verify --bundle` or equivalent customer command yet. |
| Enterprise sign-off readiness | 6/10 today, 7.5/10 with local bundle/root hash | A root hash would turn many strong local records into one signable evidence handle. |

## Why Audit Bundle Index Matters Commercially

### Enterprise Paid Adoption

Enterprise buyers do not only buy "eval results." They buy release control they can defend later. The audit bundle index is the customer-facing proof object that says:

- this release was evaluated under this policy,
- these exact inputs were used,
- these exact outputs were generated,
- this waiver was reviewed,
- this approval was signed,
- these replay cases explain the failure risk,
- this evidence was sealed at this time,
- and this root hash can verify the package later.

Without that object, A3 is still easier to position as a smart release dashboard. With it, A3 starts to look like release governance infrastructure.

### Compliance Audit

Auditors ask repeatable questions:

- What evidence was reviewed?
- Who approved it?
- Was the evidence changed after approval?
- Was the exception expired, revoked, or superseded?
- Can the retained package be verified months later?
- Can the failure be replayed or traced back to source evidence?

Input hashes, generated artifact hashes, waiver validation, and approval validation answer parts of those questions. A bundle index and root hash answer the bigger one: "Is this the same complete evidence package that existed when the decision was made?"

### Boss Sign-Off

An executive or release owner should not sign a loose folder of JSON files. They need a compact sign-off packet:

- gate decision,
- risk score,
- blocked checks,
- waiver status,
- approval status,
- expiry and follow-up owner,
- replay evidence status,
- bundle id,
- bundle root hash,
- verification command.

The root hash becomes the stable thing a boss can sign. It turns "I approved a report" into "I approved bundle `A3-BND-...` with root hash `sha256:...` under policy version `...`."

## Current A3 Evidence Chain

What A3 already has:

| Evidence layer | Current capability | Commercial meaning |
|---|---|---|
| Release Gate | `approve_release`, `needs_review`, or `block_release` with failed checks and risk score. | Customers can understand whether an agent release should ship. |
| PR Gate | GitHub Check payload shape and PR comment Markdown. | A3 can plug into engineering review flow before live GitHub writes are enabled. |
| Input hashes | Gate CLI audit manifest hashes source inputs. | Reviewers can verify the evidence used by the gate. |
| Generated artifact manifest | `a3.generated_artifact_manifest.v1` hashes generated reports and PR/GitHub-facing artifacts. | Human-facing outputs can be checked for drift. |
| Waiver validation | `a3.waiver.v1` plus `a3.waiver_review.v1` validates scope, expiry, required roles, failed-check coverage, and reviewed artifact hashes. | Exceptions become governed local evidence, not just prose. |
| Approval validation | `a3.approval.v1` plus `a3.approval_review.v1` validates exception approval, required signer roles, reviewed hashes, waiver binding, and separation of duties. | Sign-off becomes structured evidence. |
| Incident replay seed | Failed cases / top-risk case ids are included in the release workflow. | A3 has the beginning of RCA and replay workflow. |
| Redaction posture | Existing docs state no API keys, cookies, tokens, emails, or live signed media URLs should be exported. | Audit artifacts can be shared more safely with enterprise reviewers. |

This is enough for a strong paid pilot. It is not yet enough for a compliance-grade retained audit package.

## What Is Still Missing

### Bundle Index

Current A3 has multiple manifests and review records, but no single `a3.audit_bundle_index.v1` that lists every artifact by path, media type, role, SHA-256 hash, byte size, produced-by step, and inclusion status.

Needed:

- bundle id,
- release id,
- repo,
- environment,
- run id,
- head SHA,
- policy versions,
- source input artifacts,
- generated artifacts,
- waiver and waiver review,
- approval and approval review,
- redaction log,
- replay evidence,
- screenshots/PDF packet,
- GitHub/CI provenance,
- retention metadata,
- custody event log reference.

### Canonical Root Hash

Hashes exist at lower levels, but A3 lacks one canonical root hash over the ordered bundle index. Without canonicalization, two machines may hash the "same" bundle differently.

Needed:

- deterministic JSON canonicalization,
- stable artifact ordering,
- normalized paths,
- exclusion rules for the index file's own hash,
- root hash over the canonical index,
- optional detached signature over the root hash.

### Chain-of-Custody Events

A3 validates waiver and approval records, but does not yet record custody events such as generated, manifest_written, waiver_submitted, waiver_reviewed, approval_submitted, approval_reviewed, bundle_sealed, artifact_uploaded, verified, retained, expired, revoked, superseded, deleted, or legal_hold_applied.

Needed:

- append-only event schema,
- event id,
- previous event hash,
- event timestamp,
- actor identity or local attestation,
- action,
- artifact references,
- result,
- policy version,
- event hash.

### Immutable Storage And Retention

A local JSON file can be edited or deleted. Enterprise retention needs explicit storage and lifecycle semantics.

Needed:

- local immutable archive mode,
- object storage backend contract,
- WORM/object-lock option,
- retention days,
- legal hold flag,
- delete-after timestamp,
- deletion approval and deletion event,
- backup/restore instructions,
- self-host storage path policy.

### Verification Command

Customers need to verify a bundle without understanding internal code.

Needed:

- `ashr gate verify --bundle <path>`,
- `ashr gate verify --index <index.json>`,
- output showing root hash, artifact hash status, missing files, unexpected files, invalid waiver/approval references, expired evidence, and custody-chain breakage.

### GitHub Artifact Upload

GitHub dry-run check and PR comment are useful, but CI evidence should be downloadable and traceable.

Needed:

- GitHub Actions artifact upload of the sealed bundle,
- artifact name contains bundle id and short root hash,
- retention days match bundle policy,
- PR comment links to artifact and root hash,
- GitHub Check summary includes root hash and verification command,
- live mode remains behind explicit token/GitHub App approval.

### Self-Host Storage

Regulated buyers need local persistence and retention, not just files in a working tree.

Needed:

- filesystem backend for small pilots,
- SQLite/Postgres metadata index,
- S3-compatible object store option,
- encrypted-at-rest storage setting,
- RBAC for create/view/verify/delete/legal-hold,
- backup and restore drill,
- offline verification path.

### Replay Evidence

Incident replay is currently seeded by failed case ids. A compliance-grade bundle needs replay artifacts.

Needed:

- replay pack id,
- case input hashes,
- trace hashes,
- expected output hashes,
- replay command,
- replay result hashes,
- baseline/current diff hash,
- status per case: reproduced, fixed, regressed, new, flaky, not_replayed,
- replay timestamp and runner identity.

## Next Growth Points

These growth points focus on bundle index, root hash, custody, storage, retention, verification, GitHub artifact upload, self-host storage, and replay evidence.

| ID | Growth point | Why it matters | Lane |
|---|---|---|---|
| BI-1 | Add `a3.audit_bundle_index.v1` schema. | Creates the first-class index for the whole release evidence package. | Bundle schema |
| BI-2 | Include bundle id, release version, environment, repo, run id, head SHA, generated_at, and policy versions. | Prevents bundle reuse across releases or environments. | Bundle schema |
| BI-3 | Split artifacts into `source_inputs`, `generated_outputs`, `governance_records`, `custody_records`, `replay_records`, and `visual_records`. | Makes audit package structure legible to humans and machines. | Bundle schema |
| BI-4 | Record artifact role, path, content type, byte size, SHA-256, created_by step, and redaction status. | Lets auditors verify both integrity and evidence purpose. | Bundle schema |
| BI-5 | Add `required_artifacts[]` and `optional_artifacts[]` policy. | Makes missing evidence visible instead of accidental. | Bundle schema |
| BI-6 | Add bundle completeness status: complete, partial, failed, superseded. | Lets PR checks and dashboards show whether the package is usable. | Bundle schema |
| BI-7 | Include waiver and approval review statuses directly in the bundle index summary. | Gives executives one place to inspect governance state. | Bundle schema |
| BI-8 | Include redaction policy version and redaction log hash. | Proves the safety export process was part of the package. | Bundle schema |
| RH-1 | Define canonical JSON serialization for the bundle index. | Required for stable root hashes across machines. | Root hash |
| RH-2 | Add deterministic artifact ordering before root hash computation. | Prevents nondeterministic root hash drift. | Root hash |
| RH-3 | Normalize workspace-relative paths and forbid local absolute user paths. | Keeps bundles portable and safe to share. | Root hash |
| RH-4 | Compute `bundle_root_hash` over the canonical index excluding the root hash field itself. | Creates one tamper-evident handle for the package. | Root hash |
| RH-5 | Add optional detached signature over `bundle_root_hash`. | Gives enterprise buyers a stronger non-repudiation path. | Root hash |
| RH-6 | Bind waiver and approval reviewed hashes to the bundle root hash when available. | Moves sign-off from individual files to the sealed package. | Root hash |
| RH-7 | Add root hash to Markdown report, PR comment, GitHub Check payload, and management sign-off section. | Makes the evidence handle visible in the review flow. | Root hash |
| COC-1 | Add `a3.custody_event.v1` schema. | Starts an append-only history of evidence handling. | Chain of custody |
| COC-2 | Add events for gate_generated, input_manifest_written, generated_manifest_written, waiver_submitted, waiver_reviewed, approval_submitted, approval_reviewed, bundle_index_written, and bundle_sealed. | Covers the main local decision path. | Chain of custody |
| COC-3 | Add `previous_event_hash` and `event_hash`. | Makes custody tampering detectable. | Chain of custody |
| COC-4 | Add actor fields with local attestation now and GitHub/OIDC/SSO identity later. | Keeps local pilots practical while preserving enterprise upgrade path. | Chain of custody |
| COC-5 | Add events for verified, uploaded, retained, legal_hold_applied, expired, revoked, superseded, and deleted. | Covers evidence lifecycle after sign-off. | Chain of custody |
| COC-6 | Hash the custody event log into the bundle index. | Makes the custody chain part of the sealed evidence. | Chain of custody |
| IMM-1 | Add `ashr gate bundle --output <dir-or-zip>` local command shape. | Gives customers one deliverable artifact instead of scattered files. | Immutable bundle |
| IMM-2 | Package index, source manifests, generated outputs, waiver, approval, reviews, reports, replay pack, and custody log into a zip/tar archive. | Makes retention and upload practical. | Immutable bundle |
| IMM-3 | Add immutable archive naming: bundle id plus short root hash. | Makes retained artifacts easy to identify. | Immutable bundle |
| IMM-4 | Add fail-closed behavior when required bundle artifacts are missing. | Prevents incomplete packages from looking audit-ready. | Immutable bundle |
| IMM-5 | Add local write-once mode that refuses to overwrite an existing sealed bundle. | Reduces accidental evidence mutation. | Immutable bundle |
| RET-1 | Add `a3.retention_policy.v1`. | Defines how long evidence must exist and who can delete it. | Retention policy |
| RET-2 | Add retention metadata to bundle index: storage backend, retention days, legal hold, delete_after, owner, and classification. | Makes lifecycle auditable. | Retention policy |
| RET-3 | Add deletion event requiring reason, approver, timestamp, and previous bundle root hash. | Makes deletion accountable. | Retention policy |
| RET-4 | Add WORM/object-lock compatible storage option for high-compliance customers. | Supports regulated enterprise deployment. | Retention policy |
| RET-5 | Add backup/restore verification instructions. | Makes self-host retention operational instead of theoretical. | Retention policy |
| VER-1 | Add `ashr gate verify --index <index.json>`. | Lets auditors verify all indexed artifact hashes. | Verification command |
| VER-2 | Add `ashr gate verify --bundle <archive-or-dir>`. | Lets customers verify downloaded or retained bundles. | Verification command |
| VER-3 | Verification output should report root hash, missing files, hash mismatches, unexpected files, invalid schema versions, and custody-chain breaks. | Turns verification into a useful audit tool. | Verification command |
| VER-4 | Add `--json` verification output for CI and self-host automation. | Makes verification machine-readable. | Verification command |
| VER-5 | Add negative tests for tampered artifact, missing artifact, reordered canonical data, and broken previous-event hash. | Proves the verifier catches real failure modes. | Verification command |
| GH-1 | Upload sealed audit bundle as a GitHub Actions artifact in dry-run workflow docs. | Makes PR evidence downloadable without live GitHub API writes. | GitHub artifact upload |
| GH-2 | Include bundle root hash and artifact link in PR comment Markdown. | Gives reviewers direct access to the evidence package. | GitHub artifact upload |
| GH-3 | Include bundle root hash in GitHub Check summary. | Connects merge decision to sealed evidence. | GitHub artifact upload |
| GH-4 | Add GitHub artifact retention days to bundle retention metadata. | Aligns CI artifact lifecycle with compliance policy. | GitHub artifact upload |
| GH-5 | Later, persist check-run id and artifact url only behind explicit live mode. | Keeps the current no-live-GitHub boundary intact. | GitHub artifact upload |
| SH-1 | Add self-host filesystem storage backend contract. | Supports local regulated pilots quickly. | Self-host storage |
| SH-2 | Add SQLite/Postgres metadata table design for bundles, artifacts, custody events, waivers, and approvals. | Moves from working-tree files to durable audit workflow. | Self-host storage |
| SH-3 | Add S3-compatible object storage backend fields. | Supports customer-owned infrastructure. | Self-host storage |
| SH-4 | Add RBAC operations: create bundle, seal bundle, verify bundle, apply hold, delete bundle, view PII-redacted bundle. | Makes self-host governance enforceable. | Self-host storage |
| SH-5 | Add offline verification mode that does not need Ashr, GitHub, or network access. | Important for auditors and air-gapped customers. | Self-host storage |
| RP-1 | Add `a3.replay_pack.v1` schema. | Turns incident replay from case ids into executable evidence. | Replay evidence |
| RP-2 | Include case ids, input hashes, trace hashes, expected output hashes, and replay command. | Makes failure reproduction inspectable. | Replay evidence |
| RP-3 | Add replay result status: reproduced, fixed, regressed, new, flaky, not_replayed. | Lets sign-off distinguish known risk from remediated risk. | Replay evidence |
| RP-4 | Hash replay result artifacts into the bundle index. | Makes RCA evidence tamper-evident. | Replay evidence |
| RP-5 | Add replay-before-approval policy for blocked production releases. | Raises trust in exception approvals. | Replay evidence |
| UX-1 | Add management sign-off packet section with bundle id, root hash, waiver, approval, expiry, and verify command. | Makes boss sign-off fast and defensible. | Sign-off UX |
| UX-2 | Add dashboard Audit Bundle panel showing completeness, root hash, custody status, retention class, and verification result. | Makes bundle health visible without reading JSON. | Sign-off UX |
| UX-3 | Add PR comment summary for bundle completeness and verification. | Reduces reviewer friction. | Sign-off UX |

## Parallel Execution Plan

Several lanes can move at the same time because they touch different layers.

| Lane | Can start now? | First useful deliverable | Can run in parallel with |
|---|---|---|---|
| Bundle schema | Yes | `a3.audit_bundle_index.v1` JSON fixture with source, generated, waiver, approval, and replay placeholders. | Root hash, retention, replay schema |
| Root hash | Yes | Canonical serialization plus local `bundle_root_hash` over the index. | Bundle schema and verification command |
| Verification command | Yes | `ashr gate verify --index` for local file hashes and root hash. | Root hash and negative tests |
| Chain-of-custody events | Yes | Append-only local event log with previous hash and event hash. | Bundle schema and approval/waiver validation |
| Immutable packaging | Yes after schema draft | Local directory or zip bundle with no-overwrite sealed mode. | Verification and retention metadata |
| Retention policy | Yes | `a3.retention_policy.v1` fixture and fields in bundle index. | Self-host storage design |
| GitHub artifact upload | Yes in docs/workflow shape | Actions artifact upload step that uploads local sealed bundle, still no live API writes. | Root hash, PR comment summary |
| Self-host storage | Yes for design | Filesystem backend contract plus DB table sketch. | Retention, RBAC, immutable packaging |
| Replay evidence | Yes | `a3.replay_pack.v1` fixture from current failed/top-risk cases. | Bundle schema and management packet |
| Sign-off UX | Yes after root hash | Markdown management sign-off section referencing root hash and verify command. | Dashboard/PR comment work |

Suggested parallel sprint:

1. One engineer defines `a3.audit_bundle_index.v1` and a redacted fixture.
2. One engineer implements canonical root hash and `ashr gate verify --index`.
3. One engineer adds chain-of-custody event schema and local event log hashing.
4. One engineer packages a sealed local bundle directory or zip with no-overwrite behavior.
5. One engineer drafts retention/self-host storage contracts.
6. One engineer creates replay pack schema and hashes replay evidence into the bundle.
7. One engineer adds PR/GitHub Actions artifact upload wiring without live GitHub API calls.

## Commercial Impact If Main Agent Implements Local Audit Bundle Index / Root Hash

If the main agent implements a local audit bundle index and root hash, the maturity improvement is not cosmetic. It changes what A3 can honestly claim.

| Area | Before bundle/root hash | After local bundle/root hash |
|---|---|---|
| Evidence integrity | Individual inputs and generated outputs are hashed. | Whole release evidence package has one stable root hash. |
| Waiver and approval trust | Waiver/approval reference reviewed artifact hashes. | Waiver/approval can bind to a sealed bundle root hash. |
| Boss sign-off | Managers sign a report and local approval record. | Managers sign a bundle id and root hash that can be verified later. |
| Compliance audit | Auditors inspect several related artifacts. | Auditors verify one indexed, complete, tamper-evident package. |
| PR review | GitHub Check/PR comment can describe the gate. | Check/comment can point to a bundle root hash and downloadable artifact. |
| Incident replay | Failed case ids identify replay candidates. | Replay pack can be part of the sealed audit evidence. |
| Self-host readiness | Local files demonstrate contract shape. | Local bundles become a retention and storage primitive. |
| Enterprise pricing | A3 sells release intelligence and local governance. | A3 starts selling audit-grade release evidence custody. |

Estimated commercial maturity uplift:

| Dimension | Current | With local bundle index/root hash |
|---|---:|---:|
| Enterprise audit bundle readiness | 3/10 | 6.5/10 |
| Executive sign-off readiness | 6/10 | 7.5/10 |
| Compliance evidence defensibility | 6/10 | 7.5/10 |
| Self-host compliance foundation | 3.5/10 | 5/10 |
| Required-check credibility | 6.5/10 | 7/10 |
| Paid enterprise pilot readiness | 7/10 | 7.75/10 |

The key message to buyers becomes stronger:

> "A3 does not only block risky agent releases. It produces a sealed, verifiable evidence bundle showing the inputs, outputs, waiver, approval, replay evidence, and custody trail behind that decision."

## Recommended Local Implementation Sequence

Fastest money-grade sequence:

1. Add `a3.audit_bundle_index.v1` with source inputs, generated outputs, waiver, approval, redaction, and replay placeholders.
2. Compute canonical `bundle_root_hash`.
3. Add `ashr gate verify --index`.
4. Include root hash in Markdown report, PR comment, and GitHub Check payload.
5. Add custody event log with previous-event hash.
6. Package local sealed bundle directory or zip.
7. Add retention metadata.
8. Add GitHub Actions artifact upload for the sealed bundle.
9. Add replay pack schema and hash it into the index.
10. Add management sign-off packet with root hash and verify command.

Do not wait for live GitHub or live Ashr API work. The bundle/root-hash layer is valuable locally and becomes the contract that live systems can consume later.

## Final Auditor Call

A3 now has the hard beginnings of an enterprise governance product: gate decision, input hashes, generated artifact manifest, waiver validation, and approval validation. The missing layer is evidence custody.

The audit bundle index is the commercial hinge. It turns scattered valid artifacts into a single retained object. The root hash is the sign-off handle. The custody log explains how the object moved from generation to review to approval to retention. The verification command lets a buyer prove it later.

Best next step: implement a local bundle index and root hash before building live storage or live GitHub writes. It will make every later enterprise feature cleaner: branch protection, artifact upload, self-host retention, signed approvals, replay evidence, and executive sign-off can all point to the same sealed evidence package.

What this audit did not do:

- Did not modify `services/report/a3_gate_cli.mjs`.
- Did not modify `tests/a3/a3_gate_cli.test.mjs`.
- Did not modify `fixtures/a3/p3`.
- Did not modify `docs/a3/worklog.md`.
- Did not modify `docs/a3/p3_worklog.md`.
- Did not modify `docs/a3/acceptance_checklist.md`.
- Did not revert or overwrite existing changes.
- Did not call live Ashr or GitHub APIs.
- Did not read or print secret-bearing files.
