# A3 Growth-Auditor / Money-Grade Auditor: Export Redaction Firewall - 2026-07-07

## 0. Audit Scope

Role: A3 Growth-Auditor / Money-Grade Auditor.

Theme: Export Redaction Firewall.

Safety boundary followed:

- Read local repo evidence only.
- Did not read, print, summarize, or commit `.env.local`, API keys, cookies, tokens, private secret files, or live signed media URLs.
- Did not call the live ReleaseFoundry API.
- Did not call the live GitHub API.
- Wrote only this file: `docs/a3/p3_growth_auditor_redaction_firewall_2026_07_07.md`.

Evidence reviewed:

- `services/report/a3_gate_cli.mjs`
- `services/report/report_builder.mjs`
- `apps/dashboard/index.html`
- `tests/a3/a3_gate_cli.test.mjs`
- `tests/a3/report_builder.test.mjs`
- `tests/a3/dashboard_wiring.test.mjs`
- `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Prior A3 growth audits in `docs/a3/*growth*2026_07_07.md`

## 1. Executive Verdict

The Export Redaction Firewall is sellable now as an enterprise pilot control because A3 has moved beyond "please do not leak secrets" language. The Gate CLI now runs a structured redaction pass over its payload, records a redaction log, hashes input and generated artifacts, builds an audit bundle index, computes a root hash, and verifies bundle integrity. The dashboard exports also stay within a redacted-fixture model and expose JSON/CSV/Markdown downloads from local evidence.

Money-grade read: this is not yet a complete data-loss-prevention product, but it is already strong enough to sell as a release evidence firewall for AI-agent governance pilots.

Current maturity:

| Dimension | Score | Auditor read |
|---|---:|---|
| CLI export redaction | 7.5/10 | Recursive `redactValue(...)` covers emails, bearer tokens, API key assignments, cookies, `sk_`/GitHub-style tokens, and signed media URL patterns before output. |
| Export evidence integrity | 7/10 | Generated artifact manifest, bundle index, root hash, chain-of-custody hashes, and verify command exist locally. |
| Dashboard export safety | 5.5/10 | Dashboard uses `.redacted` fixtures and metadata-only signed URL posture, but lacks a centralized export sanitizer at click time. |
| Enterprise audit story | 7/10 | Secret-free exports, no live mutations, waiver/approval, bundle root hash, and verification make a credible audit packet. |
| Compliance-grade firewall | 4.5/10 | Needs policy engine, typed sensitivity taxonomy, deny-by-default export classification, SARIF/CI enforcement, attestation, and retention backend. |
| Big-money readiness | 6.5/10 | Can sell pilots to regulated AI release teams; not yet a standalone DLP/compliance platform. |

## 2. Why This Can Sell Now

Enterprise buyers pay when a control reduces release anxiety, audit labor, and secret-exposure blast radius. This round does that in four commercial ways.

1. A3 can package AI-agent release evidence without exposing keys, cookies, emails, or live signed media URLs.
2. A3 can put redacted release evidence into PR checks, PR comments, local dashboard exports, and audit bundles.
3. A3 can prove that exported artifacts are the same artifacts reviewed at sign-off by hashing generated outputs and sealing the bundle with a root hash.
4. A3 can keep the default motion local and dry-run compatible, which matters for regulated buyers that will not send traces to a SaaS evaluator during procurement.

Sellable buyer promise:

> "Before an agent release reaches customers, A3 exports a redacted, hash-verifiable evidence packet that reviewers, executives, security, and auditors can inspect without touching live secrets."

Most likely paid pilot wedges:

- AI-agent release gate for GitHub / CI.
- Audit bundle for governance review.
- Incident replay packet with redacted media metadata.
- Self-host evaluation console for regulated teams.
- Procurement evidence packet for internal AI platform teams.

## 3. What Launch Risk It Reduces

| Launch risk | How Export Redaction Firewall lowers it | Remaining risk |
|---|---|---|
| Secret leakage in CI logs | Gate CLI redacts strings before JSON/Markdown output and records replacement count. | Redaction is regex-based, not classification-based; novel token shapes can slip. |
| Live signed URL exposure | Policy blocks live signed URLs in exports; media readiness stays metadata-only unless safety is confirmed. | Dashboard has no final export-time signed URL scanner. |
| Sharing raw customer/account identifiers | Emails are scrubbed in CLI output; fixtures are committed as `.redacted`. | Names, org ids, internal ids, project names, and free-text PII need typed classification. |
| Unreviewable release artifacts | Generated artifact manifest hashes outputs; bundle index lists artifacts and computes root hash. | Needs detached signatures and immutable storage for stronger non-repudiation. |
| PR review drift | PR comment, GitHub Check payload, JSON, Markdown, and bundle outputs can be hashed together. | Live GitHub write path and branch-protection enforcement still need production hardening. |
| Accidental external mutation | Existing product posture keeps dashboard and CLI local/dry-run compatible. | Hosted integrations need explicit execution gates and audit events. |
| Audit dispute after release | Bundle verification can re-check root hash, artifact hashes, path safety, and custody chain. | Need retention/WORM backend and identity-bound approvals. |
| Media preview breach | Report builder disables live media rendering until signed URL behavior is confirmed. | Need browser-level URL allow/deny enforcement and export snapshot tests. |

## 4. Enterprise / Audit / Compliance Support

The current firewall supports these enterprise narratives:

- Release governance: redacted JSON/Markdown reports, PR check payload, PR comment, waiver review, approval review, and merge-blocking gate semantics.
- Evidence integrity: SHA-256 hashes for input artifacts, generated artifact manifest, audit bundle index, root hash, and verification command.
- Chain of custody: local event hashes in the audit bundle index show a starting custody ledger.
- Separation of duties: approval validation blocks self-approval patterns and checks required signer roles.
- Exception governance: waiver validation checks required fields, expiry, release/run binding, failed-check coverage, and approver roles.
- Data minimization: committed evidence uses `.redacted` fixtures and forbids API keys, cookies, tokens, emails, and live signed media URLs.
- Self-host procurement: local dashboard and CLI can run without live ReleaseFoundry or GitHub calls.
- Incident response: failed cases and replay queues can be packaged without exporting raw secrets.

Compliance frameworks this can credibly map to during sales, with caveats:

| Framework / buyer need | Supported today | Caveat |
|---|---|---|
| SOC 2 change management | PR gate, release gate, approval evidence, audit bundle | Need identity, retention, and CI required-check enforcement. |
| ISO 27001 change control | Release evidence, risk decision, exception record | Need policy mapping and control owner attestation. |
| SOX-style release approval | Hash-verifiable sign-off packet | Need authenticated approvers and immutable archive. |
| HIPAA / healthcare vendor review | Local redacted evidence and no-live-secret policy | Need PHI classification and customer-specific data handling. |
| Financial services model risk governance | Eval evidence, blocked-release policy, replay queue | Need model inventory linkage, policy versioning, and reviewer identity. |
| Internal AI governance board | Executive packet, no-go decision, top-risk cases | Need board-ready PDF/export package and recurring review workflow. |
| Vendor security review | Secret-free artifact bundle | Need independent scanner output and export allowlist report. |

## 5. Evidence: What Exists Now

Concrete repo evidence:

- `services/report/a3_gate_cli.mjs`: `buildGateCliPayload(...)` builds the gate payload and then calls `redactValue(...)` before returning it.
- `services/report/a3_gate_cli.mjs`: `redactText(...)` redacts API key assignments, bearer tokens, cookies, emails, token prefixes, and signed media URL-like strings.
- `services/report/a3_gate_cli.mjs`: `buildGeneratedArtifactManifest(...)` records generated artifact hashes, byte sizes, content types, and secret-free safety flags.
- `services/report/a3_gate_cli.mjs`: `buildAuditBundleIndex(...)` includes bundle artifacts, custody events, retention metadata, path safety, and a canonical SHA-256 root hash.
- `services/report/a3_gate_cli.mjs`: `verifyAuditBundleIndex(...)` verifies root hash, artifact hashes, byte sizes, unsafe paths, and custody hashes.
- `tests/a3/a3_gate_cli.test.mjs`: redaction smoke test injects email, API key assignment, bearer token, and signed URL string, then asserts they do not appear in output.
- `tests/a3/a3_gate_cli.test.mjs`: committed fixture tests assert generated artifacts are hashed, user-home paths are absent, bundle root hash exists, and verification passes.
- `services/report/report_builder.mjs`: audit bundle policy explicitly forbids API keys, cookies, tokens, emails, and live signed media URLs in exported artifacts.
- `services/report/report_builder.mjs`: release war room marks `secret_free_exports: true` and `external_mutations_enabled: false`.
- `apps/dashboard/index.html`: export buttons generate JSON/CSV/Markdown from local state loaded from `.redacted` fixtures.
- `tests/a3/dashboard_wiring.test.mjs`: dashboard wiring asserts redacted fixture filenames are loaded for request, quota, auth, frontend, media, and signed URL coverage.

## 6. What Is Still Toy-Grade And Must Be Upgraded

These pieces are useful prototypes but not yet enterprise-grade:

1. Regex redaction only. It is good for known token shapes but not enough for arbitrary PII, IDs, internal URLs, customer names, or future provider tokens.
2. No centralized export firewall library. CLI has recursive redaction, dashboard export relies on fixture discipline and builder policy.
3. No fail-closed export gate. Exports are not blocked when unclassified fields appear.
4. No sensitivity schema per field. A3 needs `public`, `internal`, `customer_sensitive`, `secret`, `signed_url`, `regulated_pii`, and `evidence_hash_only` tags.
5. No export allowlist. JSON/Markdown/CSV exports should be constructed from allowlisted fields, not whole report objects after regex cleanup.
6. No browser-side final scanner. Dashboard click export should run the same redaction/firewall scan before Blob download.
7. CSV export is thinner than JSON/Markdown. CSV can leak through flattened free text unless it gets the same sanitizer and tests.
8. No independent scanner artifact. Enterprise security teams will ask for a machine-readable "no secrets found" report.
9. No SARIF/JUnit output for CI. Required checks need standard formats.
10. No policy version registry. Redaction policy strings exist, but buyers need a versioned policy object.
11. No customer-configurable forbidden patterns. Enterprises need their own domains, account ids, project ids, and internal URL patterns.
12. No DLP-style entropy detector. High-entropy unknown secrets should be caught even when prefixes are unknown.
13. No irreversible tokenization option. Some values should become stable salted references, not plain `[REDACTED]`, so audits can correlate without exposing raw data.
14. No signed attestation. Bundle hash exists, but not an authenticated signer or detached signature.
15. No immutable retention backend. Local files are not WORM storage.
16. No role-based export permission. Anyone running dashboard can download exports if they have local file access.
17. No tenant boundary proof. Self-host story needs per-tenant policy and export audit trails.
18. No live integration quarantine. Future hosted API/GitHub paths need quarantine for raw responses before they enter report state.
19. No negative corpus. Tests need dozens of synthetic secret/PII/signed URL variants, not one smoke case.
20. No redaction diff UX. Reviewers need to see what categories were removed without seeing raw values.

## 7. Next Round: At Least 20 Growth Points

Prioritized growth backlog:

1. Build `export_firewall.mjs` as the single sanitizer for CLI, dashboard builders, GitHub payloads, PR comments, Markdown, CSV, and bundle outputs.
2. Add a field-level sensitivity registry for A3 report schema.
3. Make exports allowlist-first: export only fields marked safe for the target audience.
4. Add a fail-closed mode: unknown sensitive fields block export.
5. Run final scanner on every generated artifact before writing files.
6. Run browser-side final scanner before `download(...)` in the dashboard.
7. Add CSV-specific tests for spreadsheet formula injection, raw URLs, emails, and token fragments.
8. Add entropy-based unknown secret detection.
9. Add customer-configurable redaction patterns.
10. Add stable salted tokenization for correlation-safe identifiers.
11. Add redaction report artifact: categories, counts, fields affected, policy version, and pass/fail.
12. Add SARIF output for CI/security tools.
13. Add JUnit output for CI required checks.
14. Add `releasefoundry export scan <path>` for existing artifacts.
15. Add `releasefoundry export seal` that scans, hashes, bundles, signs, and verifies in one flow.
16. Add detached signature over bundle root hash.
17. Add identity-bound approval signing through SSO/GitHub/OIDC later.
18. Add WORM/object-lock storage backend contract.
19. Add retention policy validation and legal-hold event.
20. Add quarantine layer for raw hosted API responses before report ingestion.
21. Add dashboard export permission model for self-host mode.
22. Add audit log for every export download: actor, policy, bundle id, artifact ids, scanner status.
23. Add redaction regression corpus with 100+ synthetic patterns across providers.
24. Add media URL expiry verifier that proves links are omitted or expired before export.
25. Add procurement-ready "Export Safety Certificate" PDF/Markdown summary.
26. Add enterprise policy packs: SOC2-change, HIPAA-safe, finance-model-risk, internal-only.
27. Add OpenTelemetry/log redaction parity so runtime logs and exports follow one policy.
28. Add import scanner that refuses committed non-redacted ReleaseFoundry samples outside private refs.
29. Add path sanitizer tests across Windows/macOS/Linux home paths.
30. Add visual dashboard indicator: export safe / blocked / needs reviewer.

## 8. What Must Run In Parallel

These workstreams should not be serialized; they unlock different buyers and reduce different risks.

| Parallel lane | Why parallel | Owner profile |
|---|---|---|
| Central export firewall library | Every output path needs one policy engine. | Platform / report pipeline |
| Dashboard click-time scanner | Browser exports are customer-visible and currently less protected than CLI. | Frontend |
| CI scanner formats | SARIF/JUnit are required for enterprise required-check adoption. | DevOps / integrations |
| Sensitivity registry | Without typed fields, redaction stays regex-only. | Schema / product |
| Redaction corpus | The firewall is only as credible as its negative tests. | QA / security |
| Bundle signing and retention | Big buyers need non-repudiation and durable evidence. | Security / compliance |
| Customer policy packs | Sales needs named compliance mappings, not generic safety prose. | GTM / compliance |
| Hosted response quarantine | Future live integrations cannot wait for after-the-fact cleanup. | API / ingestion |

Hard dependency notes:

- Sensitivity registry and central firewall must land before claiming compliance-grade export safety.
- Dashboard scanner and CSV tests must land before demoing self-host exports to regulated buyers.
- SARIF/JUnit and fail-closed mode must land before positioning as a required CI check.
- Bundle signing and immutable retention must land before SOX/HIPAA/financial-services audit claims.

## 9. Closest To Big Money: Ranked

1. Regulated AI release gate with redacted audit bundle.
   - Buyer: financial services, healthcare, insurance, enterprise SaaS.
   - Why money: direct risk-control budget; maps to release approval and audit readiness.
   - Needed next: fail-closed export firewall, SARIF/JUnit, signed bundle.

2. Self-host governance console.
   - Buyer: enterprises that cannot send traces/secrets to SaaS.
   - Why money: self-host premium and procurement urgency.
   - Needed next: dashboard export scanner, RBAC, tenant policy, retention.

3. PR-required check for agent changes.
   - Buyer: platform engineering and AI enablement teams.
   - Why money: easy wedge into existing GitHub workflow.
   - Needed next: live check execution, branch-protection docs, CI artifact upload.

4. Compliance evidence packet generator.
   - Buyer: security, internal audit, AI governance boards.
   - Why money: replaces manual evidence assembly.
   - Needed next: export safety certificate, policy packs, bundle signing.

5. Incident replay / RCA pack.
   - Buyer: SRE, support quality, agent owners.
   - Why money: operational pain after failed releases.
   - Needed next: executable replay bundle and before/after fix verification.

6. Vendor security/procurement accelerator.
   - Buyer: AI platform vendors selling into enterprise.
   - Why money: shortens security review.
   - Needed next: standardized redaction scanner output and compliance summary.

7. Standalone DLP for AI eval artifacts.
   - Buyer: security teams.
   - Why money: broad market, but harder competition.
   - Needed next: much stronger classification, integrations, and policy UX.

## 10. Failure Points

The current firewall can fail in these ways:

- Unknown secret formats not covered by regex can pass.
- Free-text fields can contain customer names, internal IDs, or regulated PII that are not email/token-shaped.
- Dashboard JSON/Markdown export can include new builder fields before the CLI redaction layer ever sees them.
- CSV export can introduce spreadsheet injection or flatten unsafe free text.
- A developer can add a new fixture that is not `.redacted` and still wire it into local state unless import checks block it.
- Bundle root hash proves artifact integrity, not that the original raw evidence was safe to export.
- Redaction replacement count proves something was scrubbed, not that everything sensitive was scrubbed.
- Local files can be edited or deleted after review without immutable storage.
- Approval identity is structured but not cryptographically authenticated.
- Policy strings are human-readable but not yet versioned, enforceable policy objects.

## 11. Money-Grade Positioning

Use this positioning now:

> "A3 is a redacted release-evidence firewall for AI agents. It lets teams export PR-ready and auditor-ready evidence without leaking secrets, while preserving artifact hashes and bundle verification for later review."

Do not overclaim:

- Do not call it full DLP yet.
- Do not claim HIPAA/SOX compliance yet.
- Do not claim live signed URL rendering is safe.
- Do not claim immutable audit retention until a WORM/object-lock backend exists.
- Do not claim identity-grade signatures until approvals are bound to authenticated identities and signed bundle roots.

## 12. Next Audit Acceptance Criteria

The next Export Redaction Firewall round should pass only if:

- CLI, dashboard, GitHub payload, PR comment, Markdown, JSON, CSV, and bundle exports all call one shared firewall.
- Every exported artifact has a scan result with policy version, blocked categories, replacement counts, and pass/fail.
- Unknown high-entropy strings fail export by default.
- Dashboard download is blocked when scanner fails.
- CSV export has formula-injection protection.
- Redaction fixtures include at least 100 synthetic secret/PII/signed URL variants.
- Generated artifacts include a redaction report in the audit bundle.
- Bundle verification checks the redaction report hash.
- CI can emit SARIF and JUnit.
- Docs clearly separate "redacted evidence firewall" from "full regulatory compliance."

## 13. Bottom Line

This is a real commercial wedge. The current Export Redaction Firewall reduces the most obvious launch-killing risk: accidentally exporting secrets or live signed media URLs while trying to prove agent release quality. It also creates the foundation for enterprise auditability by hashing generated artifacts, sealing an audit bundle, and verifying that bundle later.

The closest money is not "better dashboard export." The closest money is "regulated agent release evidence that security, audit, and executives can approve without seeing raw secrets." Build the shared firewall, fail-closed scanner, CI formats, signed bundle, and retention backend in parallel; that turns this from a strong pilot into a compliance-budget product.
