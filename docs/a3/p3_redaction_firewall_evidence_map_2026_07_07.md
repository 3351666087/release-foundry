# A3 P3 Export Redaction Firewall Evidence Map - 2026-07-07

Scope: local evidence map only. This pass did not read `.env.local`, did not print secrets, and did not add runtime code or fixtures. Target output is the future Export Redaction Firewall: a fail-closed scanner/scrubber for every A3 export surface.

## Executive Finding

A3 already has strong redaction evidence for the Gate CLI path, but the firewall is not yet universal.

- `services/report/a3_gate_cli.mjs` has a recursive output scrubber: `buildGateCliPayload()` builds the payload and applies `redactValue(rawPayload)` before return (`services/report/a3_gate_cli.mjs:13`, `services/report/a3_gate_cli.mjs:48`, `services/report/a3_gate_cli.mjs:80`). The returned `redaction_log` records `applied`, `replacement_count`, and policy (`services/report/a3_gate_cli.mjs:83`).
- `services/report/report_builder.mjs` emits broad JSON, Markdown, and CSV export data, including `expected`, `actual`, `tool_call_diffs`, and `media_evidence`, but does not itself call a shared redaction firewall (`services/report/report_builder.mjs:2799`, `services/report/report_builder.mjs:3246`, `services/report/report_builder.mjs:3280`, `services/report/report_builder.mjs:3315`).
- `tests/a3/a3_gate_cli.test.mjs` already proves the CLI redacts email, API-key assignment, bearer token, and signed URL samples before output (`tests/a3/a3_gate_cli.test.mjs:654`).
- `docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md` already names this exact missing item: add redaction regression for JSON/Markdown/CSV exports and block new official-demo fixtures until export redaction exists (`docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md:89`, `docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md:124`).

## Export Surfaces To Scan

The firewall should scan both in-memory export payloads and written files.

1. `services/report/report_builder.mjs`
   - `buildJsonReport(...)` emits `schema_version: "a3.export_report.v1"` and top-level fields: `summary`, `coverage`, `evidence_readiness`, `request_provenance`, `usage_quota`, `media_readiness`, `cloud_console_shell`, `official_releasefoundry_gap`, `official_frontend_mirror`, `official_code_crawl_parity`, `official_parity_roadmap`, `release_gate`, `release_workflow`, `release_war_room`, `incident_replay_queue`, `reviewer_workflow_board`, `observability_replay_matrix`, `regression_factory`, `failure_clusters`, and `cases` (`services/report/report_builder.mjs:3280`).
   - High-risk `cases[]` fields are `expected`, `actual`, `tool_call_diffs`, and `media_evidence` (`services/report/report_builder.mjs:3315`). These can carry copied prompt/output/tool/media metadata if upstream fixtures regress.
   - `buildMarkdownReport(...)` renders a human export with release, evidence, media, cloud, official parity, failure clusters, and case summaries (`services/report/report_builder.mjs:2799`).
   - `buildCsvReport(...)` emits `run_id`, `case_id`, `scenario_id`, `title`, `status`, `score`, `severity`, `primary_failure_class`, `failure_summary`, `media_types`, `media_evidence_count`, and `vm_stream_count` (`services/report/report_builder.mjs:3246`). CSV needs formula-injection checks in addition to secret checks.
2. `services/report/a3_gate_cli.mjs`
   - `buildGateCliPayload(...)` scans the whole payload via recursive `redactValue(...)` before returning (`services/report/a3_gate_cli.mjs:80`).
   - `renderGateCliMarkdown(...)` renders the already-redacted CLI payload into Markdown (`services/report/a3_gate_cli.mjs:91`).
   - `writeRequestedOutputs(...)` writes `json_report`, `markdown_report`, `github_check_run`, and `pr_comment_markdown`, then optionally writes `generated_artifact_manifest` and `audit_bundle_index` (`services/report/a3_gate_cli.mjs:868`).
   - `buildGithubCheckRunPayload(...)` emits Check Run annotations with `title`, `message`, and JSON `raw_details` (`services/report/a3_gate_cli.mjs:845`). It currently depends on upstream redacted fields.
   - `buildGeneratedArtifactManifest(...)`, `buildAuditBundleIndex(...)`, and `verifyAuditBundleIndex(...)` are export-adjacent surfaces because they publish paths, hashes, safety flags, and findings.
3. `fixtures/a3/p3`
   - Existing committed export fixtures to scan: `a3_gate_cli_mock_blocked.redacted.json`, `a3_gate_cli_report.redacted.md`, `a3_gate_cli_pr_comment.redacted.md`, `a3_gate_cli_github_check.redacted.json`, `a3_gate_cli_generated_artifact_manifest.redacted.json`, `a3_audit_bundle_index_blocked_exception.redacted.json`, `a3_audit_bundle_verification_passed.redacted.json`, `a3_release_war_room_11926.redacted.json`.
   - Real-ReleaseFoundry redacted source evidence to scan before report export: request/run/dataset/media/frontend mirror/code crawl fixtures under `fixtures/a3/p3/*.redacted.json`.
4. `docs/a3`
   - Human-written evidence docs are also export-like artifacts. Priority docs include `p3_gate_cli_growth_2026_07_07.md`, `p3_generated_artifact_manifest_growth_2026_07_07.md`, `p3_audit_bundle_index_growth_2026_07_07.md`, `p3_audit_bundle_verifier_growth_2026_07_07.md`, `p3_release_war_room_growth_2026_07_07.md`, `p3_signed_media_url_coverage.md`, and this file.
5. `tests/a3`
   - `tests/a3/a3_gate_cli.test.mjs` is the primary place to expand CLI/firewall assertions.
   - `tests/a3/report_builder.test.mjs` is the primary place to add JSON/Markdown/CSV firewall assertions.

## Secret Patterns To Scan

Existing CLI redaction patterns live in `redactText(...)`:

- `RELEASEFOUNDRY_API_KEY=...` assignments (`services/report/a3_gate_cli.mjs:1290`).
- `Bearer ...` authorization values (`services/report/a3_gate_cli.mjs:1291`).
- `Cookie: ...` header lines (`services/report/a3_gate_cli.mjs:1292`).
- Email addresses (`services/report/a3_gate_cli.mjs:1293`).
- `sk_...`, `ghp_...`, and `github_pat_...` generic token shapes (`services/report/a3_gate_cli.mjs:1294`).
- Signed/media URLs with `X-Amz-`, `Signature=`, `signed_url`, `token=`, or `expires=` markers (`services/report/a3_gate_cli.mjs:1282`, `services/report/a3_gate_cli.mjs:1295`).

Additional patterns the firewall should add before it is called complete:

- `Authorization:` headers, not only `Bearer` text.
- lowercase or mixed-case key assignments such as `api_key=`, `token=`, `access_token=`, `refresh_token=`, `session=`, and `secret=`.
- OAuth query parameters such as `access_token`, `id_token`, `refresh_token`, `client_secret`, and `code`.
- Cookie-like fields in JSON: `cookie`, `set-cookie`, `session_id`, `csrf`, `xsrf`, `jwt`.
- cloud signed URL families beyond the current pattern: AWS `X-Amz-Signature`, GCS `X-Goog-Signature`, Azure SAS `sig=`, generic `expires` plus `signature`.
- local absolute paths and user-home leakage: Windows drive paths, `/Users/`, `C:/Users/`, backslash variants, and temp dirs from generated output tests.
- CSV formula injection prefixes for exported cell values: `=`, `+`, `-`, `@`, tab, and carriage return.
- raw official source or copyrighted code snippets in official mirror/code-crawl exports.
- live account identifiers that are not secrets but should stay out of external bundles: raw email, tenant/user ids, organization names, and browser storage keys.

## Existing Redaction Evidence

Code evidence:

- `redactValue(...)` is recursive across strings, arrays, and objects (`services/report/a3_gate_cli.mjs:1255`). This is a good extraction point for a shared `export_redaction_firewall.mjs`.
- `buildGateCliPayload(...)` includes `audit_manifest.redaction_policy` stating that API keys, cookies, tokens, emails, and live signed media URLs are not allowed in CLI output (`services/report/a3_gate_cli.mjs:71`).
- `writeOutputArtifact(...)` converts paths to workspace-relative portable paths and records `sha256` plus `byte_size` (`services/report/a3_gate_cli.mjs:960`).
- `normalizePortablePath(...)` blocks absolute paths by replacing them with `[outside-workspace]/basename` (`services/report/a3_gate_cli.mjs:988`).
- `buildChainOfCustodyEvents(...)` records generated artifact hashing and governance review events (`services/report/a3_gate_cli.mjs:1016`).

Fixture evidence:

- `fixtures/a3/p3/releasefoundry_signed_media_url_coverage.redacted.json` records `safety.signed_url_values_saved=false`, `raw_urls_saved=false`, `headers_saved=false`, `cookies_saved=false`, and `tokens_saved=false` (`fixtures/a3/p3/releasefoundry_signed_media_url_coverage.redacted.json:5`).
- That same signed URL coverage fixture confirms only file signed URL samples and blocks live rendering with `conclusion.render_live_signed_links_in_a3=false` (`fixtures/a3/p3/releasefoundry_signed_media_url_coverage.redacted.json:50`).
- `fixtures/a3/p3/a3_release_war_room_11926.redacted.json` records `safety.secret_values_saved=false`, `raw_tokens_saved=false`, `raw_cookies_saved=false`, `raw_signed_urls_saved=false`, and `official_source_committed=false` (`fixtures/a3/p3/a3_release_war_room_11926.redacted.json:111`).
- `fixtures/a3/p3/releasefoundry_frontend_mirror_summary.redacted.json` declares a clean-room boundary and sets `secret_values_allowed=false`, `raw_cookies_allowed=false`, `raw_tokens_allowed=false`, and `raw_signed_urls_allowed=false` (`fixtures/a3/p3/releasefoundry_frontend_mirror_summary.redacted.json:5`, `fixtures/a3/p3/releasefoundry_frontend_mirror_summary.redacted.json:224`).
- `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json` records `safety.contains_secret_values=false`, `local_absolute_paths_allowed=false`, and a redaction policy forbidding API keys, cookies, tokens, emails, and live signed media URLs (`fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json:219`).
- `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json` records generated artifact safety with `contains_secret_values=false` and `local_absolute_paths_allowed=false` (`fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json:51`).

Test evidence:

- `tests/a3/a3_gate_cli.test.mjs` asserts input artifacts are hashed, paths start with `fixtures/`, and `audit_manifest.redaction_policy` includes `No API keys` (`tests/a3/a3_gate_cli.test.mjs:54`).
- The strict-exit CLI test asserts audit artifact paths do not include `Users/` (`tests/a3/a3_gate_cli.test.mjs:99`).
- The generated artifact manifest test asserts output paths do not include the temp dir or `Users/`, hashes are valid, and safety flags are false for secret values and absolute paths (`tests/a3/a3_gate_cli.test.mjs:383`).
- The audit bundle test asserts bundle artifacts include source/governance/generated artifacts, exclude the self-index, and avoid `Users/` plus Windows drive prefixes (`tests/a3/a3_gate_cli.test.mjs:553`).
- The verifier test asserts committed bundle verification passes and renders Markdown evidence (`tests/a3/a3_gate_cli.test.mjs:571`).
- The tamper test asserts root hash and artifact hash mismatches fail verification (`tests/a3/a3_gate_cli.test.mjs:592`).
- The sensitive-string smoke test asserts email, `RELEASEFOUNDRY_API_KEY=...`, bearer token, and signed URL strings are absent after `buildGateCliPayload(...)` (`tests/a3/a3_gate_cli.test.mjs:654`).
- The committed PR artifact test asserts the check, comment, report, manifest, bundle, and verification fixtures keep expected shape and no generated artifact/bundle path includes `Users/` (`tests/a3/a3_gate_cli.test.mjs:692`).
- `tests/a3/report_builder.test.mjs` asserts release workflow audit bundle policy includes `No API keys` (`tests/a3/report_builder.test.mjs:143`).
- `tests/a3/report_builder.test.mjs` asserts release war room export says `enterprise_readiness.secret_free_exports=true`, `external_mutations_enabled=false`, and committed fixture safety flags save no secret values or raw signed URLs (`tests/a3/report_builder.test.mjs:192`, `tests/a3/report_builder.test.mjs:207`).
- `tests/a3/report_builder.test.mjs` asserts official frontend mirror safety disallows secret values and raw tokens (`tests/a3/report_builder.test.mjs:989`, `tests/a3/report_builder.test.mjs:1006`).
- `tests/a3/report_builder.test.mjs` asserts official code crawl parity does not commit official source or raw source excerpts (`tests/a3/report_builder.test.mjs:1026`).
- `tests/a3/report_builder.test.mjs` asserts media readiness blocks live rendering and cloud shell disables real mutations and secret values (`tests/a3/report_builder.test.mjs:1118`, `tests/a3/report_builder.test.mjs:1136`).

Docs evidence:

- `docs/a3/p3_gate_cli_growth_2026_07_07.md` documents output files, workspace-relative paths, and the lightweight output redaction scrubber (`docs/a3/p3_gate_cli_growth_2026_07_07.md:45`).
- The same doc names the gap: output redaction is lightweight pattern scrubbing, not a full DLP engine (`docs/a3/p3_gate_cli_growth_2026_07_07.md:139`).
- `docs/a3/p3_signed_media_url_coverage.md` records that no raw signed URL values are saved and live signed URL rendering remains blocked.
- `docs/a3/p3_growth_auditor_2026_07_07.md` names the enterprise gap: no evidence that redaction fails closed when a secret-like value survives scrub.

## Gaps And Failure Points

- No shared firewall module. `redactValue(...)` is private to `a3_gate_cli.mjs`; `report_builder.mjs` has no reusable scrub/scan/fail-closed entry point.
- No fail-closed behavior. The current CLI replaces known patterns and reports a count, but it does not scan after redaction and throw/block when suspicious residue remains.
- JSON/Markdown/CSV report builder exports are not proven secret-safe against injected fixture content. `buildJsonReport(...)` includes `expected`, `actual`, `tool_call_diffs`, and `media_evidence`, which are the highest-risk fields.
- CSV export has no formula-injection guard.
- Current signed URL detection is pattern-based and may miss provider-specific SAS/GCS/AWS variants or lowercase query names.
- Current token detection covers `sk`, `ghp`, and `github_pat`, but not many common secret prefixes or JSON key names.
- Path hygiene is proven mainly for CLI-generated artifacts and bundle records, not for every docs/report export path.
- Redaction log is count-only; it lacks field path, pattern id, replacement id, source surface, and whether scanning was pre/post-redaction.
- No fixture-level redaction scanner contract for `fixtures/a3/p3/*.redacted.json` before those fixtures feed reports.
- No explicit scanner for `docs/a3` evidence files, even though docs are external-facing artifacts.
- No live GitHub writer yet, so future GitHub Check/PR writer must reuse the firewall before any token-backed call.
- No policy knob for strictness by surface: local dashboard display, local audit bundle, PR comment, GitHub check, and external customer bundle may need different allowed fields.

## Recommended Testable Assertions

Add these as focused tests in `tests/a3/a3_gate_cli.test.mjs` and `tests/a3/report_builder.test.mjs`.

1. `buildJsonReport(...)` must remove or replace `RELEASEFOUNDRY_API_KEY=...` when the string appears under `cases[].actual.final_response`.
2. `buildJsonReport(...)` must remove or replace `Bearer ...` when the string appears under `cases[].expected`.
3. `buildJsonReport(...)` must remove or replace `Cookie: ...` when the string appears under `tool_call_diffs[].actual.arguments`.
4. `buildJsonReport(...)` must remove or replace email addresses in `failure_summary`, `title`, `expected`, and `actual`.
5. `buildJsonReport(...)` must remove or replace `sk_...`, `ghp_...`, and `github_pat_...` strings anywhere in nested case objects.
6. `buildJsonReport(...)` must replace live signed URLs under `media_evidence.evidence_items[].url`, `media_evidence.evidence_items[].signed_url`, and `actual`.
7. `buildMarkdownReport(...)` must not contain raw API key, bearer token, cookie, email, GitHub token, signed URL, local absolute path, or `Users/` when source fixtures include injected sentinel strings.
8. `buildCsvReport(...)` must not contain raw secret-like sentinels and must neutralize formula-leading cell values such as `=`, `+`, `-`, `@`, tab, or carriage return in `title` and `failure_summary`.
9. `buildGateCliPayload(...)` must fail closed or return a blocking `redaction_findings` status when post-redaction scan still finds a high-confidence sentinel.
10. `renderGateCliMarkdown(...)` must be scanned after rendering, not only before, because Markdown formatting can concatenate strings from multiple fields.
11. `writeRequestedOutputs(...)` must scan every generated file body before `writeOutputArtifact(...)` writes it.
12. `buildGeneratedArtifactManifest(...)` must keep `safety.contains_secret_values=false` only when the generated artifact scan passes; otherwise it must mark false unsafe or block writing.
13. `buildAuditBundleIndex(...)` must include a hash of the redaction findings log in the bundle or explicitly record that no findings were present.
14. `verifyAuditBundleIndex(...)` must fail if bundle artifacts include absolute paths, `Users/`, or `[outside-workspace]` artifacts marked as required customer-deliverable files.
15. A fixture scan over `fixtures/a3/p3/*.redacted.json` must pass for known secret patterns, signed URLs, raw cookies/tokens, and local user-home paths.
16. A docs scan over `docs/a3/*.md` must pass for raw key/token/cookie/signed URL patterns while allowing literal pattern names in code ticks.
17. Official mirror/code-crawl exports must fail if they include source excerpts longer than a small allowed threshold or fields named as raw source/content.
18. GitHub Check annotations must not include `expected`, `actual`, raw tool arguments, raw URL, or account identifiers beyond case id, severity, failure class, and run id.
19. The redaction log must include field paths for every replacement, including arrays such as `cases[0].actual.final_response`.
20. The scanner must be idempotent: scanning an already-redacted export should produce zero new replacements and no blocking findings.

## Concrete Test Entry Points

- Extend `tests/a3/a3_gate_cli.test.mjs` near `A3 gate CLI redacts sensitive strings before output` (`tests/a3/a3_gate_cli.test.mjs:654`) with nested payload cases and post-render checks.
- Extend `tests/a3/report_builder.test.mjs` near the report export tests that already call `buildJsonReport(...)`, `buildMarkdownReport(...)`, and `buildCsvReport(...)` (`tests/a3/report_builder.test.mjs:149`, `tests/a3/report_builder.test.mjs:153`, `tests/a3/report_builder.test.mjs:525`, `tests/a3/report_builder.test.mjs:530`).
- Reuse committed redacted fixtures from `fixtures/a3/p3` as safe baselines, then inject synthetic sentinel strings in-memory inside tests rather than committing new secret-looking fixture values.
- Add a scan helper that walks `fixtures/a3/p3`, `docs/a3`, generated temp files, and report strings, with an allowlist for literal documentation text such as `RELEASEFOUNDRY_API_KEY` without a value.

## Implementation Hook Recommendation

The smallest low-risk implementation path is:

1. Extract `redactValue(...)` and `redactText(...)` from `services/report/a3_gate_cli.mjs` into a shared report service module, for example `services/report/export_redaction_firewall.mjs`.
2. Add `scanValue(...)` and `scanText(...)` that return findings with `surface`, `path`, `pattern_id`, `severity`, and `replacement`.
3. Add `redactExport(value, { surface, failClosed })` that returns `{ value, findings, replacement_count, blocked }`.
4. Call it from `buildGateCliPayload(...)` before return, preserving current behavior but upgrading `redaction_log`.
5. Add safe variants for `buildJsonReport(...)`, `buildMarkdownReport(...)`, and `buildCsvReport(...)`, or route those builders through an export wrapper used by CLI/dashboard/download code.
6. Scan rendered strings and written files as the final boundary; do not rely only on structured pre-render values.

## Still Worth Hitting Next

- Full DLP-style fail-closed export mode.
- Structured redaction findings log with field paths.
- Export-surface registry so new JSON/Markdown/CSV/PDF/PR/GitHub outputs cannot bypass the firewall.
- Redaction log hashing in generated artifact manifests and audit bundle index.
- CSV injection hardening.
- Fixture/doc scanner in CI.
- GitHub live writer preflight that requires a clean firewall result before any token-backed API call.
- More signed URL provider patterns and per-modality media preview policy once audio/image/video samples are safely redacted.
