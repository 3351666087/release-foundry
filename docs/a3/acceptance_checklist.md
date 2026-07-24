# A3 Acceptance Checklist

## Qwen2.5 7B real-model evaluation - 2026-07-23

- [x] Run a larger local model through the same A1/A2/A3 pipeline as the baseline.
- [x] Preserve the exact sandbox order, amount, tool and Judge semantics.
- [x] Capture a fresh Run ID, Tool Call, Trace, Judge results and A3 reports.
- [x] Confirm the 7B model response explicitly identifies the sandbox boundary.
- [x] Present the real run as a Chinese five-step evidence story before technical tables.
- [x] Read visible model, run, latency, tool, receipt, Judge and score facts from the imported run.
- [x] Show real source excerpts and path/line anchors from command launch through A3 export.
- [x] Explain the observable model-processing boundary without claiming hidden chain-of-thought.
- [x] Render a dynamic runtime receipt with command, model, HTTP endpoint, latency, Tool Call, Trace, Judges and verdict.
- [x] Verify desktop and 390 x 844 rendering with no horizontal overflow.
- [x] Record the 0.5B versus 7B difference as an observation, not a broad ranking claim.
- [x] Keep model weights, runtime output, secrets and private data out of Git.
- [ ] Add a repeated multi-scenario benchmark before publishing a model leaderboard.

## Docker local-model refund demo - 2026-07-23

- [x] Keep the fixed failed refund fixture as an offline presentation fallback.
- [x] Run a real local model through the existing Python SDK adapter in Docker.
- [x] Restrict the only executable refund tool to one synthetic order and amount.
- [x] Record that no real order, payment provider, bank, WeChat Pay, or Alipay mutation occurs.
- [x] Generate a fresh A1 RunResult with one Tool Call and four ordered Trace events.
- [x] Grade the same case with the existing five A2 Judges without changing A2 semantics.
- [x] Preserve the same `run_id` and `case_id` across A1, A2, A3, reports, and API import.
- [x] Export A3 JSON, Markdown, CSV, and a local Hosted Report.
- [x] Add `live-refund-demo` to the product data-source selector.
- [x] Repair misleading real-payment model claims and record the repair in Agent metadata.
- [x] Preserve Chinese text through Windows PowerShell UTF-8 API import.
- [x] Normalize A1 `agent_output.text` as A3 actual output and deduplicate Tool Calls.
- [x] Verify desktop and 390 x 844 rendering with four Trace events and one Tool Call.
- [x] Ignore runtime output and keep generated evidence free of secrets and real customer data.
- [ ] Connect to a real payment sandbox only after authorization, tenant identity, RBAC, durable audit, and explicit product approval exist.

## New A3 Lane Goal / Trusted Resource Isolation - 2026-07-12

- [x] Read the new A3 Lane Goal and preserve it as the continuing enterprise
  Product / Workflow / Commercial UI mandate.
- [x] Confirm GitHub `main` is `ccf6ce5` through the official connector after
  direct Git HTTPS was reset.
- [x] Confirm local and remote-main strategy blob is `575b31b8`.
- [x] Keep A1 as identity/runtime/usage/deploy authority.
- [x] Keep A2 as grade/evidence/Decision Ledger/Release Decision authority.
- [x] Keep A2 `release_ready=false` and do not recompute Release Ready in A3.
- [x] Require a per-request server-side principal resolver in hosted mode.
- [x] Require trusted, authenticated, active, unexpired principal state.
- [x] Require explicit effective permissions and actor/subject reference.
- [x] Reject browser role/header/query/body authority in hosted mode.
- [x] Make hosted `source` lookup exact with no foreign snapshot fallback.
- [x] Validate organization, tenant, workspace, project, and environment
  before returning tenant-owned data.
- [x] Compare report source and all five scope fields.
- [x] Support colliding report IDs through a scope-aware internal key.
- [x] Prove colliding run/case/report IDs cannot cross tenants.
- [x] Ignore client report-view time and use the server clock.
- [x] Prove expired share tokens cannot be backdated into an allowed state.
- [x] Persist metadata-only denial audit for unknown hosted routes.
- [x] Align runtime 401/403 with closed OpenAPI denial schemas.
- [x] Technically prevent demo mode from performing live GitHub mutations.
- [x] Preserve dry-run GitHub planning in demo mode.
- [x] Default direct server startup to hosted enforcement regardless of
  `NODE_ENV`; require an explicit setting for demo mode.
- [x] Disable standalone CLI live GitHub publication before token or network
  access and keep the workflow example dry-run/read-only.
- [x] Require an A2 release-ready, chain-verified Decision Ledger record and
  current ledger selectors before live GitHub transport.
- [x] Require a server-side A2 authority resolver, A1 trusted worker, and
  tenant-bound GitHub installation target for hosted live publication.
- [x] Prove self-consistent local A2 allow JSON cannot authorize transport.
- [x] Reject exception approval when only a foreign-scope waiver ID exists.
- [x] Keep the merged-main A2 `release_ready=false` fixture blocked from live
  publication.
- [x] Exclude foreign and legacy unscoped audit/admin/review/readback/GitHub/
  import records from hosted aggregates.
- [x] Persist source and all five scope fields on newly created aggregate
  records and their metadata-only audit receipts.
- [x] Expose `a3.aggregate_scope_status.v1` with honest `partial` status and
  excluded counts.
- [x] Normalize Partial state in the typed Webapp client and render a
  Chinese-first retry path.
- [x] Prove the Partial banner is bounded on desktop and 390 x 844 mobile.
- [x] Persist access decisions across SQLite restart as local durability proof.
- [x] Persist GitHub publish receipts and event-outbox rows in dedicated SQLite
  tables and verify them with direct SQL queries after restart.
- [x] Preserve two same-name sources across different five-level tenant scopes.
- [x] Scope A1/A2 import idempotency namespaces by source plus tenant scope.
- [x] Validate runtime/OpenAPI parity for all `53/53` protected operations and
  enforce permission equality with the RBAC registry.
- [x] Report fixture storage as `db_ready=false`; reserve true for SQLite.
- [x] Render Partial-scope warning before empty data state.
- [x] Clear stale Webapp data and distinguish 401/403/404/network/server states.
- [x] Save Chinese 401/403 screenshots without account or secret data.
- [x] Full A3 Node suite passes (`387/387`).
- [x] Webapp typecheck and production build pass.
- [x] Fresh-port Playwright suite passes (`33/33`).
- [x] A1 TypeScript session lifecycle passes (`35/35`).
- [x] A2 trusted spine passes (`7/7`).
- [x] Commercial and hygiene CL guards pass.
- [x] Changed-file real-format long token/key scan reports zero matches;
  credential-shaped negative-test fixtures remain redacted test inputs.
- [x] `.env.local` remains ignored and absent from Git status.
- [x] `git diff --check` passes.
- [ ] Wire the hosted resolver to a deployed A1 session/service-account
  verifier; the current interface is not production identity proof.
- [ ] Replace memory/SQLite authority with PostgreSQL and forced RLS.
- [x] Replace source-only snapshot keys with a source plus five-level scope
  composite identity and prove same-source multi-tenant coexistence locally.
- [ ] Persist all five scope columns in authoritative SQL tables and enforce
  them in every repository query.
- [x] Generate and validate exact runtime-route/OpenAPI parity (`53/53`).
- [x] Audit malformed JSON and protected OPTIONS attempts consistently in the
  local hosted-reference path; production ingress/CORS/RLS proof remains open.
- [ ] Prove customer IdP, multi-instance, object custody, GitHub worker,
  deployment, upgrade, rollback, backup, and restore in a customer-like VPC.

## Round 12 Request Boundary - 2026-07-12

- [x] Authenticate and authorize hosted protected mutations before consuming
  their request body.
- [x] Preserve sanitized `401/403` precedence for missing identity, permission,
  or five-level scope.
- [x] Return fixed metadata-only `400` for authorized malformed JSON.
- [x] Require `application/json` and return fixed `415` otherwise.
- [x] Require a top-level JSON object and return fixed `422` for null, arrays,
  strings, and numbers.
- [x] Enforce a default 1 MiB streaming body limit with fixed `413`.
- [x] Enforce a default 10 second body-read deadline with fixed `408`.
- [x] Persist `request_body_state`, decision, status, canonical operation,
  transport method, preflight target, and metadata-only five-level scope.
- [x] Keep raw body, identity, token, cookie, origin, path parameters, and
  client-selected audit source out of persisted access events.
- [x] Resolve protected `OPTIONS` against `Access-Control-Request-Method`
  before returning `204`.
- [x] Reject missing/unsupported/unregistered protected preflight targets with
  sanitized audit-backed failures.
- [x] Keep public health preflight distinct from protected routes.
- [x] Add closed OpenAPI `400/408/413/415/422` responses and protected OPTIONS
  metadata to all 53 runtime RBAC operations.
- [x] Document sanitized fail-closed `503` when authorization configuration or
  access-audit persistence is unavailable.
- [x] Keep runtime/OpenAPI parity at `53/53`.
- [x] Run focused Node request-boundary tests (`44/44`).
- [x] Run the full A3 Node suite (`397/397`).
- [x] Run the CI-mainline Webapp/HTTP Playwright spec (`10/10`).
- [x] Run the full fresh-port Playwright suite with one worker (`35/35`).
- [x] Pass Webapp TypeScript and Next.js production build (14 pages).
- [x] Pass A1 TypeScript session lifecycle (`35/35`) and A2 trusted spine
  (`7/7`) without changing either lane's semantics.
- [x] Pass commercial and hygiene CL checks with no findings.
- [x] Record independent Money-Grade findings, remediation, capability levels,
  and 24 next-round growth points.
- [ ] Generate the redacted request-boundary evidence from a runtime probe with
  receipt IDs, hashes, commit SHA, and verifier output.
- [ ] Prove dual-Origin browser CORS/CSRF behavior behind a production-like
  ingress and deployed A1 principal verifier.
- [ ] Move authoritative audit custody to PostgreSQL with five-level columns,
  forced RLS, transactional outbox, retention, backup, and restore proof.

## G2.3 Dashboard Skeleton

- [x] `apps/dashboard` exists.
- [x] Dashboard can load local fixture JSON.
- [x] Dashboard shows summary metrics.
- [x] Dashboard shows Run List.
- [x] Dashboard shows Case Detail.
- [x] Dashboard shows Expected vs Actual.
- [x] Dashboard shows Trace Timeline.
- [x] Dashboard shows Failure Clusters.
- [x] Dashboard exposes JSON/CSV/Markdown export actions.
- [x] Dashboard exposes 7 filters: status, family, failure class, run, severity, score band, judge mode.
- [x] Dashboard shows per-judge drilldown for selected cases.
- [x] `services/report` contains shared report/normalization logic.
- [x] `tests/a3` verifies summary, clustering, and export shapes.
- [x] `tests/a3` verifies filter options and filter behavior.
- [x] Browser screenshot evidence captured under `docs/screenshots`.

## G2 Contract Safety

- [x] No real Ashr API calls.
- [x] No real keys or secrets.
- [x] A1 runner logic not modified.
- [x] A2 judge semantics not modified.
- [x] A1/A2 draft PR branches not merged.
- [x] A3 mock fixtures cite A1/A2 PR source paths.

## A3 Release Evidence / Audit Display

- [x] Latest `origin/main` merged before this round's A3 changes.
- [x] `services/report/report_builder.mjs` can summarize GitHub Check publish evidence.
- [x] `services/report/report_builder.mjs` can summarize GitHub PR comment publish evidence.
- [x] `services/report/report_builder.mjs` can summarize required-check rollout plan evidence.
- [x] `services/report/report_builder.mjs` can summarize audit bundle verification evidence.
- [x] `services/report/report_builder.mjs` can summarize signed audit archive verification evidence.
- [x] JSON reports include `release_evidence_summary`.
- [x] Markdown reports include `## Release Evidence Summary`.
- [x] Dashboard includes a `Release Evidence` panel.
- [x] Dashboard loads existing redacted release evidence fixtures for static sources.
- [x] Report Center includes Release Evidence status.
- [x] Print-ready report includes Release Evidence status.
- [x] Dashboard wrapping hardened for long release ids, check names, and verification badges.
- [x] Screenshot evidence saved under `docs/screenshots/a3-dashboard-release-evidence-2026-07-08.png`.
- [x] Tests verify release evidence export does not include raw GitHub request details.
- [x] Tests verify dashboard release evidence wiring.
- [x] GitHub publish receipts remain clearly labeled as dry-run / not posted.
- [x] No real Ashr, GitHub, billing, auth, or cloud mutation API was called in this display round.
- [x] API-backed dashboard payload includes sanitized `release_evidence_summary`.
- [x] Added `GET /api/a3/releases/:releaseId/evidence-summary` response contract.
- [x] Hosted reports include immutable `release_evidence_snapshot` metadata.
- [x] Hosted report HTML renders Release Evidence only for active/shareable reports.
- [x] Denied hosted report pages still do not render report body or case evidence.
- [x] Report Center manifest includes `release_evidence_summary` artifact evidence.
- [x] Artifact Registry treats `release_evidence_summary` as a first-class report artifact.
- [x] SQL migration contract includes `release_evidence_summaries`.
- [x] SQLite-backed A3 store persists release evidence summary rows.

## P3 Ashr Calibration

- [x] Confirmed `.env.local` exists and is ignored.
- [x] Did not print, document, or commit the Ashr key.
- [x] Ran minimal read-only Ashr SDK smoke test.
- [x] Confirmed `init()` and `health_check()` succeed.
- [x] Confirmed `list_datasets()`, `list_runs()`, and `list_requests()` return usable field shapes.
- [x] Saved sanitized fixtures under `fixtures/a3/p3`.
- [x] Documented P3 plan in `docs/a3/p3_ashr_calibration_plan.md`.
- [x] Documented field mapping in `docs/a3/p3_field_mapping.md`.
- [x] Documented worklog and evidence in `docs/a3/p3_worklog.md`.
- [x] Added small P3 mapper in `services/report/p3_ashr_mapper.mjs`.
- [x] Added mapper tests in `tests/a3/p3_ashr_mapper.test.mjs`.
- [x] Confirmed existing A3 report builder tests still pass.
- [x] Confirmed new P3 mapper tests pass.
- [x] Checked native backend failure-class evidence with a real failing run; current sample has grade metrics/reason but no named backend `failure_class`, so A3 derives the class.
- [x] Decide score source: prefer Ashr grade score; use `semantic_similarity` only as provisional action-results fallback.
- [x] Join dataset scenario titles into mapped A3 cases.

## P3 Product Console / Media Evidence

- [x] Recorded ROI decision before implementation.
- [x] Selected one highest ROI enhancement for this round: media evidence.
- [x] Saved sanitized media calibration fixtures under `fixtures/a3/p3`.
- [x] Confirmed real sample includes `audio`, `file`, `action_tags`, `output_path`, and `vm_stream`.
- [x] Documented media calibration in `docs/a3/p3_media_calibration.md`.
- [x] Documented official frontend observation in `docs/a3/p3_official_frontend_notes.md`.
- [x] Extended P3 mapper to support `run.result.cases[]`.
- [x] Extended P3 mapper to emit `media_evidence`.
- [x] Extended P3 mapper to emit media timeline events.
- [x] Extended report export to preserve media evidence in JSON/CSV.
- [x] Added P3 media sample test coverage.
- [x] Dashboard can switch between A1/A2 mock and P3 media sample.
- [x] Dashboard shows product console overview.
- [x] Dashboard shows Usage / Quota known-gap panel.
- [x] Dashboard shows Requests / Datasets / Runs object summary.
- [x] Dashboard shows case-level Media Evidence panel.
- [x] Browser smoke test confirmed P3 media sample renders.
- [x] Mobile viewport check confirmed no horizontal overflow at width 390.
- [x] Screenshots saved under `docs/screenshots`.
- [x] Authenticated Ashr Lab dashboard observed after manual login through isolated Chrome/CDP.
- [x] Audited signed media URL coverage in `docs/a3/p3_signed_media_url_coverage.md`.
- [x] Confirmed `signed_url` field for file-like dataset actions.
- [ ] Native signed media URL field confirmed for audio/image/video.
- [x] Added read-only media API recalibration fixture under `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`.
- [x] Added signed URL refresh fixture under `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`.
- [x] Confirmed official frontend Usage page exposes Images, Audio, and Files quota channels.
- [x] Confirmed Usage frontend functions: `get_usage` and `billing_get_status`.
- [x] Confirmed direct API-key calls to `get_usage` and `billing_get_status` are OAuth-gated with 403 responses.
- [x] Added A3 Usage / Quota dashboard panel wiring from redacted P3 evidence.
- [x] Added Usage / Quota evidence to JSON and Markdown reports.
- [x] Added Usage / Quota section to print-ready report preview.
- [x] Saved Usage / Quota dashboard screenshot under `docs/screenshots/a3-dashboard-usage-quota-media.png`.

## P3 Frontend / API Product Logic

- [x] Saved current read-only frontend/API calibration sample under `fixtures/a3/p3/ashr_frontend_api_objects.redacted.json`.
- [x] Saved current redacted run detail sample under `fixtures/a3/p3/ashr_run_trace_sample.redacted.json`.
- [x] Saved current signed media URL field probe under `fixtures/a3/p3/ashr_media_url_sample.redacted.json`.
- [x] Confirmed `get_run` can return a direct run object with `result.cases[]`.
- [x] Confirmed signed URL field name appears as `actions[].signed_url` in at least one dataset action.
- [x] Saved signed URL coverage summary under `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`.
- [x] Saved read-only failed run/request probes under `fixtures/a3/p3`.
- [x] Confirmed real failed run fields: `run.result.status`, `cases[].status`, `cases[].grade.passed`, `cases[].grade.score`, `cases[].grade.reason`, and `cases[].grade.metrics`.
- [x] Confirmed A3 mapper can consume API probe `response.run` failed-run fixture shape.
- [x] Documented frontend page map in `docs/a3/p3_frontend_page_map.md`.
- [x] Documented frontend workflow in `docs/a3/p3_frontend_workflow_notes.md`.
- [x] Documented frontend field mapping in `docs/a3/p3_frontend_field_mapping.md`.
- [x] Documented A3 MVP recommendations in `docs/a3/p3_a3_mvp_recommendations.md`.
- [x] Documented frontend-to-A3 gap analysis in `docs/a3/p3_frontend_to_a3_mvp_gap.md`.
- [x] Documented API-vs-frontend visibility gap in `docs/a3/p3_api_frontend_visibility_gap.md`.
- [x] Documented Chinese P3/A3 handoff summary in `docs/a3/p3_status_handoff_cn.md`.
- [x] Direct authenticated Lab page content scrape after manual login, using isolated Chrome/CDP instead of Codex in-app browser.
- [x] Saved redacted frontend session-expired network probe under `fixtures/a3/p3/ashr_frontend_session_expired_network.redacted.json`.
- [x] Confirmed an earlier frontend session-expired state required fresh manual login before deeper page observation.
- [x] Documented relogin observation checklist in `docs/a3/p3_frontend_relogin_observation_checklist.md`.
- [x] Confirmed fresh manual relogin restored frontend access and returned `200` for top-level Lab/frontend API calls.
- [x] Saved redacted relogin top-level summary under `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`.
- [x] Confirmed fresh logged-in frontend still has no UI-visible populated dataset/run.
- [x] Confirmed authenticated Lab tabs: Datasets, Agents, Folders, Analytics, Usage, Trust, API Keys, Team.
- [x] Confirmed New Dataset opens an 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.
- [x] Recovered from in-app-browser Google login stall by using isolated normal Chrome plus local CDP after manual login.
- [x] Crawled authenticated top-level Lab pages through the normal Chrome session without saving cookies, tokens, API keys, or raw account values.
- [x] Filled a minimal official New Dataset wizard draft to the Review step for `A3 Refund Demo Dataset` / `A3 Refund Demo Agent`.
- [x] Confirmed official media input configuration includes text, audio, file, image, video, website simulation, and custom schema.
- [x] Confirmed official tool configuration fields: tool name, description, parameter name, parameter type, parameter description, optional marker.
- [x] Saved redacted wizard-review evidence under `fixtures/a3/p3/ashr_chrome_agent_wizard_review.redacted.json`.
- [x] With explicit user confirmation, clicked official `Generate Test Suite`.
- [x] Confirmed hosted dataset became UI-visible as `A3 Refund Demo Dataset`, display id `#00000374`, dataset id `884`.
- [x] Confirmed generated dataset has 5 frontend-visible test cases covering text, audio, file, and image evidence.
- [x] Saved post-generation frontend/API evidence under `fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json` and `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`.
- [x] Confirmed official `Results (0)` / no runs found state after generation.
- [x] Created a hosted run result for generated dataset `884` and saved redacted run evidence as run `11925`.
- [x] Confirmed run `11925` exposes pass/fail, score, expected vs actual, tool-call, trace-like observations, and media evidence fields through the API sample.
- [x] Added `P3 Official Demo 884/11925` as a selectable dashboard source.
- [x] Confirmed the official demo source renders 1 run, 5 cases, 2 pass, 3 fail, 40% pass rate, and 56.4 average score.
- [x] Saved official demo dashboard screenshot under `docs/screenshots/a3-dashboard-official-demo-884-11925.png`.
- [x] Attempted direct official frontend revisit for dataset `884` after run `11925`; saved redacted relogin-needed evidence under `fixtures/a3/p3/ashr_dataset_884_frontend_relogin_needed.redacted.json`.
- [x] Observed authenticated official dataset `884` frontend in normal Chrome after relogin.
- [x] Confirmed official Test cases tab shows 5 generated refund cases with title, case key, description, action count, and tag count.
- [x] Confirmed official case detail shows TEST DETAILS, tags, ACTIONS, User/Agent actors, TEXT/AUDIO labels, and Tool Calls.
- [x] Confirmed official Results still shows `Results (0)` / `No runs found`; API run `11925` is not visible in the official Results UI.
- [x] Saved authenticated frontend observation under `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`.
- [x] Documented official-vs-A3 dashboard gap analysis in `docs/a3/p3_official_dashboard_gap_analysis.md`.
- [x] Added dashboard Official Ashr Gap panel for copied/partial/blocked/out-of-scope product areas.
- [x] Added `official_ashr_gap` to report JSON and Official Ashr Gap to Markdown/print report output.
- [x] Saved Official Ashr Gap dashboard screenshot under `docs/screenshots/a3-dashboard-official-gap.png`.
- [x] Added Media Readiness dashboard panel with channel, evidence, VM stream, signed URL, and live-rendering safety status.
- [x] Added Cloud Console Shell dashboard panel for read-only auth/workspace/team/API-key/billing/trust/cloud-mutation boundaries.
- [x] Added `media_readiness` and `cloud_console_shell` to JSON reports.
- [x] Added Media Readiness and Cloud Console Shell sections to Markdown/print report output.
- [x] Added per-channel Media Readiness Matrix for audio/files/images/video/VM stream decisions.
- [x] Added Cloud Action Guardrails for local exports vs disabled login/API-key/team/billing/trust/cloud actions.
- [x] Documented media/cloud console polish in `docs/a3/p3_media_cloud_console_polish.md`.
- [x] Saved Media/Cloud polish screenshot under `docs/screenshots/a3-dashboard-media-cloud-polish.png`.
- [x] Saved Cloud Shell screenshot under `docs/screenshots/a3-dashboard-cloud-shell.png`.
- [x] Saved Media Channel Matrix screenshot under `docs/screenshots/a3-dashboard-media-matrix.png`.
- [x] Saved Cloud Action Guardrails screenshot under `docs/screenshots/a3-dashboard-cloud-guardrails.png`.
- [x] Added A3 Request Provenance summary from real redacted Ashr request fields.
- [x] Dashboard shows Request Provenance for P3 media sample source.
- [x] JSON and Markdown exports include Request Provenance when available.
- [x] Created official-UI-compatible hosted run `11926` using `result.tests[].action_results[]`.
- [x] Confirmed `get_run(11926)` exposes 5 tests, expected vs actual, tool-call comparisons, pass/fail, score, and media metadata through redacted API evidence.
- [x] Confirmed `list_runs(dataset_id=884, summary_only=true)` returns run `11926`, matching the frontend-style list-runs call shape.
- [x] Updated `P3 Official Demo 884/11926` as the selectable dashboard source.
- [x] Confirmed local dashboard renders run `11926` with 1 run, 5 cases, 2 pass, 3 fail, 40% pass rate, 56.4 average score, and 5 media-evidence cases.
- [x] Saved official demo dashboard screenshot under `docs/screenshots/a3-dashboard-official-demo-884-11926.png`.
- [ ] Visually confirm in a logged-in official Ashr frontend whether dataset `884` Results now lists run `11926`; API summary evidence is confirmed, but the in-app browser was logged out.
- [x] Added commercial Release Gate summary with approve/review/block decisions.
- [x] Added Release Gate to JSON, Markdown, and print/PDF report output.
- [x] Added Release Gate dashboard panel.
- [x] Confirmed run `11926` correctly blocks release with risk score `70`.
- [x] Added tests for blocked risky evidence and approved clean evidence.
- [x] Saved Release Gate screenshot under `docs/screenshots/a3-dashboard-release-gate-11926.png`.
- [x] Added `release_workflow` JSON export with GitHub check, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay pack.
- [x] Added PR Gate / Review Workflow to Markdown report output.
- [x] Added PR Gate & Audit dashboard panel.
- [x] Added PR Gate & Audit Workflow to print/PDF report preview.
- [x] Added tests for release workflow packaging and dashboard wiring.
- [x] Documented PR Gate workflow growth in `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`.
- [x] Saved PR Gate & Audit screenshot under `docs/screenshots/a3-dashboard-pr-gate-audit-11926.png`.
- [x] Added command-shaped gate entrypoint in `services/report/a3_gate_cli.mjs`.
- [x] Added configurable commercial thresholds fixture in `fixtures/a3/release_gate_thresholds.json`.
- [x] Added threshold-aware release gate output.
- [x] Added hashed CLI audit manifest for input files.
- [x] Added workspace-relative artifact paths to avoid local absolute path leakage.
- [x] Added `--strict-exit` mode for CI-controlled nonzero process exits.
- [x] Added `--no-fail` mode for local report generation.
- [x] Added CLI output files for JSON, Markdown, GitHub Check payload, and PR comment Markdown.
- [x] Added GitHub Check annotations for top-risk cases.
- [x] Added lightweight CLI output redaction scrubber.
- [x] Saved redacted GitHub Check and PR comment artifacts under `fixtures/a3/p3`.
- [x] Saved redacted CLI evidence in `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`.
- [x] Added CLI tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented CLI growth in `docs/a3/p3_gate_cli_growth_2026_07_07.md`.
- [x] Added dry-run GitHub Check Run request builder in `services/report/a3_github_integration.mjs`.
- [x] Added dry-run PR comment upsert planner in `services/report/a3_github_integration.mjs`.
- [x] Added GitHub Actions workflow example in `docs/a3/p3_github_action_workflow_example.yml`.
- [x] Saved redacted dry-run GitHub request fixtures under `fixtures/a3/p3`.
- [x] Added GitHub dry-run adapter tests in `tests/a3/a3_github_integration.test.mjs`.
- [x] Documented GitHub dry-run integration growth in `docs/a3/p3_github_dry_run_integration_2026_07_07.md`.
- [x] Added `--output-manifest` to the A3 Gate CLI.
- [x] Added generated artifact manifest schema `a3.generated_artifact_manifest.v1`.
- [x] Added hashes for generated JSON, Markdown, GitHub Check, and PR comment artifacts.
- [x] Saved redacted generated artifact manifest under `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`.
- [x] Added generated artifact manifest tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented generated artifact manifest growth in `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`.
- [x] Added `--waiver` and `--generated-at` to the A3 Gate CLI.
- [x] Added file-backed waiver validation schema `a3.waiver.v1`.
- [x] Added waiver review output schema `a3.waiver_review.v1`.
- [x] Added waiver expiry and required-approver validation.
- [x] Saved redacted waiver request and waiver review fixtures under `fixtures/a3/p3`.
- [x] Added waiver validation tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented waiver validation growth in `docs/a3/p3_waiver_validation_growth_2026_07_07.md`.
- [x] Added `--approval` to the A3 Gate CLI.
- [x] Added file-backed approval record schema `a3.approval.v1`.
- [x] Added approval review output schema `a3.approval_review.v1`.
- [x] Added approval decision, signer role, artifact hash, waiver binding, and separation-of-duties validation.
- [x] Saved redacted approval record and approval review fixtures under `fixtures/a3/p3`.
- [x] Added approval validation tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented signed approval validation growth in `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md`.
- [x] Added `--output-bundle` to the A3 Gate CLI.
- [x] Added audit bundle index schema `a3.audit_bundle_index.v1`.
- [x] Added canonical bundle root hash generation.
- [x] Added chain-of-custody event hashes with previous-event links.
- [x] Added artifact grouping for source inputs, generated outputs, governance records, and custody records.
- [x] Saved redacted audit bundle fixture under `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`.
- [x] Added audit bundle tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented audit bundle index growth in `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`.
- [x] Added `--verify-index` to the A3 Gate CLI.
- [x] Added audit bundle verification schema `a3.audit_bundle_verification.v1`.
- [x] Added root hash, artifact hash, byte-size, and custody-chain verification.
- [x] Saved redacted audit bundle verification fixture under `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`.
- [x] Added verifier tests in `tests/a3/a3_gate_cli.test.mjs`.
- [x] Documented audit bundle verifier growth in `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`.
- [x] Add live-capable GitHub Check Run publisher and CLI with dry-run default and sanitized receipts.
- [x] Update GitHub Actions example to publish the Ashr++ Release Gate check using a runtime `GITHUB_TOKEN`.
- [x] Save redacted dry-run publish receipt under `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json`.
- [x] Add live-capable PR comment publisher behind explicit `--pr-comment --pull-number` opt-in.
- [x] Add dry-run branch-protection required-check plan for `Ashr++ Release Gate`.
- [x] Save redacted PR comment receipt and required-check plan fixtures under `fixtures/a3/p3`.
- [x] Add `github_publish_evidence` to JSON and Markdown reports.
- [x] Add GitHub check/comment/required-check artifacts to Artifact Registry and dashboard Report Center wiring.
- [ ] Configure repository branch protection to require the `Ashr++ Release Gate` check after maintainer approval.
- [x] Persist hash-sealed reviewer waiver/approval records through A3 API, store, SQLite, dashboard, and JSON export.
- [ ] Verify real cryptographic reviewer signatures and identity binding before accepting approvals as production sign-off.
- [ ] Add file hashes for generated PDF and screenshot export artifacts.
- [x] Add signed immutable audit archive manifest and archive verifier.
- [x] Save redacted signed archive manifest and verification fixtures under `fixtures/a3/p3`.
- [x] Add archive manifest signature, root-hash, entry-hash, missing-entry, and CLI tests.
- [ ] Add binary zip/tar packaging around the signed archive manifest.

## P3 Trace / Tool-Call Diff

- [x] Added `buildToolCallDiffs()` to compare expected vs actual tool calls.
- [x] Added statuses for match, missing tool, unexpected tool, wrong tool, and wrong arguments.
- [x] Added report JSON export field `tool_call_diffs`.
- [x] Added dashboard Tool Call Diff panel in Case Detail.
- [x] Added test coverage for missing required tool.
- [x] Added test coverage for wrong arguments.
- [x] Browser smoke confirmed missing-tool and wrong-arguments cases render.
- [x] Screenshot saved under `docs/screenshots/a3-p3-tool-call-diff.png`.
- [x] Add field-level argument diff highlighting.
- [x] Added field-level argument diffs to JSON export.
- [x] Added test coverage for changed, missing, and unexpected argument fields.
- [x] Link each diff row back to A2 judge evidence.
- [x] Added judge evidence links to JSON export.
- [x] Dashboard shows judge mode, score, summary, details, remediation, and tool call IDs for matched diff rows.
- [x] Added semantic matching for reordered tool calls.
- [x] Dashboard shows tool-call match strategy and original expected/actual positions.
- [x] Added mock `wrong_tool_order` case to exercise the matching behavior.
- [x] Deep-link judge evidence to exact trace event IDs when shared trace IDs are available.

## A3 Product Console Polish

- [x] Added product-console polish documentation.
- [x] Refined dashboard visual hierarchy and metric health styling.
- [x] Added Coverage Health panel using optional A2 coverage fixture data.
- [x] Added Triage Queue panel for highest-priority failed cases.
- [x] Added Report Center panel explaining JSON/CSV/Markdown outputs.
- [x] Shared export logic across topbar and Report Center buttons.
- [x] Added dashboard wiring test coverage for new operations panels.
- [x] Added P3 mapper de-duplication for repeated redacted case IDs.
- [x] Added Judge Mode filter using normalized A2 judge modes.
- [x] Browser-smoke updated desktop dashboard.
- [x] Browser-smoke updated P3 media dashboard.
- [x] Browser-smoke updated mobile dashboard.
- [x] Capture updated screenshots under `docs/screenshots`.
- [x] Added PDF/print-ready Report Preview section.
- [x] Added Print Report / Print-PDF actions.
- [x] Added print CSS that hides interactive dashboard controls.
- [x] Browser-smoke print-ready report preview.
- [x] Added Request Provenance panel using P3 request fixture fields.
- [x] Added Official Frontend Mirror clean-room dashboard panel.
- [x] Added `official_frontend_mirror` JSON export field.
- [x] Added Official Frontend Mirror Markdown and print/PDF report sections.
- [x] Wired `ashr_frontend_mirror_summary.redacted.json` into dashboard data loading.
- [x] Added report-builder and dashboard-wiring tests for the frontend mirror summary.
- [x] Browser-smoke verified the Official Frontend Mirror panel with 11 navigation items and 7 API groups.
- [x] Saved Official Frontend Mirror screenshot under `docs/screenshots/a3-dashboard-official-frontend-mirror.png`.
- [x] Added Release War Room summary schema `a3.release_war_room.v1`.
- [x] Added `release_war_room` JSON export field.
- [x] Added Release War Room Markdown and print/PDF report sections.
- [x] Added Release War Room dashboard panel.
- [x] Added redacted War Room fixture for official demo dataset `884` / run `11926`.
- [x] Added Growth-Auditor Release War Room artifact.
- [x] Added report-builder and dashboard-wiring tests for Release War Room.
- [x] Browser-smoke verified Release War Room with `No-go`, 4 metrics, 4 executive brief lines, and 6 lanes.
- [x] Saved Release War Room screenshot under `docs/screenshots/a3-dashboard-release-war-room.png`.
- [x] Added `official_parity_roadmap` JSON export field.
- [x] Added Official Parity Roadmap Markdown and print/PDF report sections.
- [x] Added Official Parity Roadmap dashboard panel.
- [x] Added Media Evidence Queue inside Media Readiness.
- [x] Added report-builder tests for Official Parity Roadmap and Media Evidence Queue.
- [x] Added dashboard-wiring tests for Official Parity Roadmap and Media Evidence Queue.
- [x] Re-ran A3 report tests against A1-style run/tool-call data and A2 G3 grade/coverage fixtures.
- [x] Browser-smoke verified Official Parity Roadmap with 6 priority rows and Media Evidence Queue with 5 queued cases.
- [x] Saved Official Parity Roadmap screenshot under `docs/screenshots/a3-dashboard-official-parity-media-queue.png`.
- [x] Saved Media Evidence Queue screenshots under `docs/screenshots/a3-dashboard-media-evidence-queue.png` and `docs/screenshots/a3-dashboard-media-evidence-queue-detail.png`.
- [x] Added Incident Replay Queue summary schema `a3.incident_replay_queue.v1`.
- [x] Added `incident_replay_queue` JSON export field.
- [x] Added Incident Replay Queue Markdown and print/PDF report sections.
- [x] Added Incident Replay dashboard panel.
- [x] Added reviewer packet artifacts per replay case.
- [x] Added report-builder tests proving A1 trace/tool-call evidence and A2 judge evidence are packaged into replay queue.
- [x] Added dashboard-wiring tests for Incident Replay.
- [x] Browser-smoke verified Incident Replay Queue with 3 queued official-demo failed cases and 6 replay steps.
- [x] Saved Incident Replay Queue screenshot under `docs/screenshots/a3-dashboard-incident-replay-queue.png`.
- [x] Added Reviewer Workflow Board summary schema `a3.reviewer_workflow_board.v1`.
- [x] Added `reviewer_workflow_board` JSON export field.
- [x] Added Reviewer Workflow Board Markdown and print/PDF report sections.
- [x] Added Reviewer Workflow dashboard panel.
- [x] Added reviewer lane, review state, missing-artifact, waiver-state, approval-readiness, and next-action fields.
- [x] Calibrated Reviewer Workflow against A1 trace/tool-call evidence and A2 judge/coverage evidence.
- [x] Added report-builder tests proving A1/A2 evidence drives reviewer workflow state.
- [x] Added dashboard-wiring tests for Reviewer Workflow.
- [x] Browser-smoke verified Reviewer Workflow with `Blocked`, 3 open official-demo items, 6 reviewer lanes, and A1/A2 calibration counts.
- [x] Saved Reviewer Workflow screenshot under `docs/screenshots/a3-dashboard-reviewer-workflow-board.png`.
- [x] Added Official Code Crawl Parity summary schema `a3.official_code_crawl_parity.v1`.
- [x] Added redacted code-crawl fixture from official frontend mirror structure and keyword counts.
- [x] Added `official_code_crawl_parity` JSON export field.
- [x] Added Official Code Crawl Parity Markdown and print/PDF report sections.
- [x] Added Official Code Crawl dashboard panel.
- [x] Verified code-crawl parity preserves clean-room boundary and does not commit official source.
- [x] Calibrated code-crawl parity targets against A1 run/trace/tool-call data and A2 score/failure/judge data.
- [x] Added report-builder and dashboard-wiring tests for Official Code Crawl.
- [x] Browser-smoke verified Official Code Crawl with 9 chunk rows, 6 parity target rows, and `source committed no`.
- [x] Saved Official Code Crawl screenshot under `docs/screenshots/a3-dashboard-official-code-crawl-parity.png`.
- [x] Added Observability Replay Matrix summary schema `a3.observability_replay_matrix.v1`.
- [x] Added `observability_replay_matrix` JSON export field.
- [x] Added Observability Replay Matrix Markdown and print/PDF report sections.
- [x] Added Observability Replay dashboard panel.
- [x] Added replay lanes for trace timeline, tool errors, latency/duration, A2 judge link, media metadata, and official Observability parity.
- [x] Added per-case observability replay items with production risk, observability state, trace/tool/error/judge/media counts, official parity source, and next action.
- [x] Calibrated Observability Replay against A1 trace/observation/tool-call evidence and A2 score/pass-fail/failure/judge evidence.
- [x] Calibrated Observability Replay against official clean-room Observability code-crawl signals without copying source.
- [x] Added report-builder and dashboard-wiring tests for Observability Replay.
- [x] Browser-smoke verified Observability Replay after official-demo dashboard load.
- [x] Saved Observability Replay screenshot under `docs/screenshots/a3-dashboard-observability-replay-matrix.png`.
- [x] Added Regression Factory summary schema `a3.regression_factory.v1`.
- [x] Added `regression_factory` JSON export field.
- [x] Added Regression Factory Markdown and print/PDF report sections.
- [x] Added Regression Factory dashboard panel.
- [x] Added regression candidates that derive from Incident Replay and Observability Replay evidence.
- [x] Calibrated regression candidates against A1 trace/tool-call evidence, A2 judge/coverage evidence, and official Results review parity.
- [x] Added generated suite plan, required contracts, proposed assertions, and next action per candidate.
- [x] Added report-builder and dashboard-wiring tests for Regression Factory.
- [x] Browser-smoke verified Regression Factory after official-demo dashboard load.
- [x] Saved Regression Factory screenshot under `docs/screenshots/a3-dashboard-regression-factory.png`.
- [x] Added shared Export Redaction Firewall module for report and gate outputs.
- [x] Added `export_redaction_firewall` JSON export field.
- [x] Added Export Redaction Firewall Markdown and print/PDF report sections.
- [x] Added Export Safety dashboard panel.
- [x] Added CSV secret scrubbing and spreadsheet formula hardening.
- [x] Reused the shared export firewall from the A3 Gate CLI.
- [x] Split dashboard into `index.html`, `src/app.mjs`, and `src/styles.css`.
- [x] Reduced dashboard HTML from more than 3,000 lines to about 400 lines.
- [x] Strengthened direct A1 RunResult compatibility.
- [x] Strengthened direct A2 single-run plus single-grade compatibility.
- [x] Added focused tests for raw A1 and raw A2 compatibility.
- [x] Added dashboard Data option for raw A1 RunResult.
- [x] Added dashboard Data option for raw A2 single-case fixture.
- [x] Added dashboard wiring tests for raw A1/A2 sources.
- [x] Browser-smoke verified raw A1 and raw A2 dashboard sources.
- [x] Saved raw A2 dashboard screenshot under `docs/screenshots/a3-dashboard-raw-a2-source.png`.

## Next Acceptance Targets

- [x] Replace A3 mock fixtures with generated fixtures from merged A1/A2 outputs.
- [x] Add case-level judge drilldown.
- [x] Add severity and score-band filters.
- [x] Add judge-mode filter after A2 exposes more varied judge-mode cases.
- [x] Expand from current 4 screenshots to 10 demo screenshots.
- [x] Add a dashboard data-source option that loads raw A1/A2 fixtures directly.
- [x] Add an API-backed dashboard source that can serve the current A3 normalized payload through `/api/a3/dashboard`.
- [x] Add a DB-ready store abstraction with memory, JSON-file, and fixture-backed implementations.
- [x] Add a shareable hosted report payload with redaction, hashes, report metadata, and share URL path.
- [x] Add dashboard component boundary for SaaS Runtime instead of keeping every new UI block inside the main app module.
- [x] Add tests for A3 store, A3 API server, shareable report payloads, and dashboard API wiring.
- [x] Add SaaS Admin Console shell for login, cloud/project management, usage, API key metadata, team, and trust.
- [x] Add `GET /api/a3/admin/console` and `POST /api/a3/admin/actions/plan`.
- [x] Keep SaaS admin actions safe: real login, API-key creation, team invites, billing mutations, and Trust publishing are disabled or plan-only.
- [x] Add A1/A2 compatibility counts inside SaaS Admin Console.
- [x] Add Auth Session, RBAC Matrix, Invite Workflow, Usage Controls, API Key Lifecycle, Trust Center, Cloud Management, and Product Console Map to SaaS Admin dashboard rendering.
- [x] Add SaaS database migration-contract tables for `users`, `roles`, `team_members`, `api_keys`, and `trust_reports`.
- [x] Keep SaaS admin and cloud-management parity clean-room: no official private source, no real account data, and no cloud mutations committed.
- [x] Add Product Console workflow model for onboarding, project console, audit log, and commercial readiness.
- [x] Add `GET /api/a3/product/console`.
- [x] Wire Product Console into API-backed dashboard payload and dashboard UI.
- [x] Add A1/A2 compatibility evidence for Product Console workflow.
- [x] Add Growth-Auditor artifact with at least 20 next growth points for onboarding/audit/project console.
- [x] Add Product Console workflow state to JSON, Markdown, and print/PDF report exports.
- [x] Add SaaS Admin login/team/usage/API-key/trust/cloud guardrails to JSON, Markdown, and print/PDF report exports.
- [x] Confirm Product Console and SaaS Admin exports still derive readiness from A1 run evidence and A2 judge evidence.
- [x] Add Growth-Auditor artifact with 40 next growth points for Product Console artifact/export entry.
- [x] Add Artifact Registry model for report exports and control-plane evidence.
- [x] Add `GET /api/a3/artifacts/registry`.
- [x] Add `artifact_registry_entries` and `artifact_lifecycle_events` to the SQL migration contract.
- [x] Show Artifact Registry summary and entries in Report Center.
- [x] Include Artifact Registry evidence in JSON, Markdown, and print/PDF report exports.
- [x] Add Growth-Auditor artifact with 45 next growth points for Artifact Registry commercialization.
- [x] Add CI export-firewall scans for generated docs and fixtures.
- [x] Add a real local SQL adapter target using Node SQLite, while keeping Postgres/MySQL production migration tooling as future work.
- [x] Add hosted report page rendering for `/reports/:reportId` or `/r/:shareToken`.
- [x] Add API import routes for new A1 RunResult and A2 GradeResult uploads.
- [x] Add Enterprise Readiness report schema and dashboard panel for self-host/audit review.
- [x] Add self-host console contract artifact and document-contract tests.
- [x] Add idempotency keys and validation error shapes to A1/A2 import routes.
- [x] Add view audit event and expiry/revocation policy for hosted reports.
- [x] Add SQL adapter contract artifact for idempotency ledger, audit events, share/revoke/view tables, and usage ledger.
- [x] Add API calibration evidence artifact for import validation/error shapes.
- [x] Add SQL migration contract generator for Postgres, MySQL, and SQLite targets.
- [x] Add read-only usage ledger meters for runs, cases, trace events, tool-call cases, judge results, hosted reports, report views, revocations, and API imports.
- [x] Add report center manifest contract for hosted report artifacts, usage ledger evidence, and DB migration evidence.
- [x] Add Report Center index/control-plane API for hosted report lifecycle, manifest readiness, usage, migration, and redaction status.
- [x] Wire Report Center index into API-backed dashboard after hosted report creation.
- [x] Add external `/r/:shareToken` hosted report route with token-hash lookup.
- [x] Keep raw share tokens out of stored report payloads and durable Report Center summaries.
- [x] Record allowed and denied share-link view audit events for active, expired, revoked, and missing tokens.
- [x] Add dashboard Report Center revoke controls for active API-backed hosted reports.
- [x] Verify SQLite-backed A3 store can persist A1/A2 imports, hosted report lifecycle, audit events, and usage ledger rows.
- [x] Add safe SaaS Admin action request workflow for login/team/usage/API-key/trust/cloud-management operations.
- [x] Add `POST /api/a3/admin/actions/submit` and `GET /api/a3/admin/actions`.
- [x] Persist `saas_admin_action_requests` in the SQL migration contract and SQLite-backed A3 store.
- [x] Add dashboard Record Request / Record Guardrail controls without enabling real Ashr cloud mutations.
- [x] Include SaaS Admin action request summary in JSON/Markdown/print-ready exports.
- [x] Confirm SaaS Admin action requests preserve A1/A2 compatibility and do not store secrets, emails, tokens, cookies, or real API keys.
- [x] Add Gate CLI inputs for GitHub Check publish receipt, PR-comment publish receipt, and required-check plan.
- [x] Seal GitHub publish evidence into generated artifact manifests and audit bundle indexes with SHA-256 and byte-size evidence.
- [x] Keep GitHub publish evidence downstream of A3 delivery; do not mix it into A1 run inputs or A2 judge inputs.
- [x] Refresh stale committed Gate CLI/audit-bundle fixtures after latest `main` conflict-resolution artifact changes.
- [x] Verify A3 Gate CLI after GitHub publish evidence sealing: 21 pass, 0 fail.
- [x] Move release evidence summary from static display into A3 store/API/hosted-report/Report Center/SQLite paths.
- [x] Add release evidence health, next-action, and sanitized diff helpers.
- [x] Add local tenant-scope negative tests for release evidence API reads.
- [x] Add local tenant-scope negative tests for report detail, manifest, view, revoke, and report-list routes.
- [x] Verify SQLite report persistence stores report tenant scope instead of defaulting to `org-local`.
- [x] Redact unexpected API internal-error messages before returning them to clients.
- [x] Add explicit `a3.release_evidence_summary.v2` authority summary builder.
- [x] Keep release evidence v1 stable while serving v2 only through explicit version negotiation.
- [x] Add `GET /api/a3/releases/:releaseId/evidence-health`.
- [x] Add `GET /api/a3/releases/:releaseId/evidence-diff`.
- [x] Add A1 RunResult/Trace/ToolCall/Observation counts to v2 release evidence.
- [x] Add A2 Scenario/Judge/GradeResult/FailureTaxonomy counts to v2 release evidence.
- [x] Add A1/A2 release evidence v2 contract mapping artifact.
- [x] Add Growth-Auditor money-grade release evidence v2 audit artifact.
- [x] Add release evidence v2 SQL contract tables for snapshots, diffs, and readbacks.
- [x] Persist release evidence v2 snapshots, safe diffs, and readback placeholder rows in the SQLite-backed A3 store.
- [x] Add live-shaped GitHub Check readback contract for confirmed, stale, missing, deleted, permission-denied, and failed states.
- [x] Add live-shaped PR comment readback contract for marker/body-hash match, stale, missing, deleted, and permission-denied states.
- [x] Add required-check proof contract where plan-only cannot claim enforcement.
- [x] Wire GitHub readback receipts into release evidence v2 summaries and SQLite readback rows.
- [x] Add `POST /api/a3/releases/:releaseId/readbacks` for sanitized readback capture.
- [x] Add `GET /api/a3/releases/:releaseId/readbacks` for release-scoped readback inspection.
- [x] Add idempotency, tenant-scope 404s, audit event linkage, and nested secret redaction for readback capture.
- [x] Keep A1/A2 API import receipts separate from A3 readback capture receipts.
- [x] Persist latest readback authority rows in the SQLite-backed A3 store and reload captured readbacks from durable state.
- [x] Add `release_evidence_readbacks` usage meter and `release_evidence_readback` artifact registry entries.
- [x] Document readback capture API in `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`.
- [x] Add safe readback capture CLI for CI/worker usage with dry-run default and explicit `--submit`.
- [x] Add dashboard payload `release_evidence_readbacks` so API-backed UI can display captured readback records.
- [x] Add readback records, status counts, and resource counts to Release Evidence JSON/Markdown exports.
- [x] Add readback rows to dashboard Release Evidence panel and print/PDF-ready report.
- [x] Add tests proving dashboard/report/store/API readback visibility does not leak tokens, emails, Authorization headers, or raw secret values.
- [x] Document that readback evidence is downstream of A1/A2 and does not replace A1 RunResult or A2 GradeResult proof.
- [x] Document readback worker and visibility round in `docs/a3/p3_readback_worker_and_visibility_2026_07_08.md`.
- [x] Add CL commercial anchor gate in `scripts/cl_guard.py commercial`.
- [x] Wire CL commercial anchor gate into `.github/workflows/cl-gate.yml`.
- [x] Add CL guard tests for A3 commercial anchors, A3/TypeScript/evidence routing, and missing-anchor failures.
- [x] Ensure the TypeScript SDK CI job installs Go before running cross-stack TS-to-Go vertical-slice tests.
- [x] Document A1/A2/A3 CL contract alignment in `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md`.
- [x] Document TypeScript, Tailwind/CSS, Playwright, mobile, and WeChat CL gaps in `docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md`.
- [x] Add Growth-Auditor CL gate report in `docs/a3/p3_growth_auditor_cl_gate_2026_07_09.md`.
- [x] Keep Playwright, Tailwind, Expo, and WeChat checks advisory-only until their toolchains exist.
- [x] Export A2 result persistence manifest in A3 JSON and Markdown reports.
- [x] Export A2 release unblock checklist in A3 JSON and Markdown reports.
- [x] Wire dashboard report export to load A2 persistence and unblock fixtures without changing A2 judge semantics.
- [x] Add A3 Commercial Growth Manifest in `services/report/a3_commercial_growth_manifest.mjs`.
- [x] Test A3 Commercial Growth Manifest in `tests/a3/a3_commercial_growth_manifest.test.mjs`.
- [x] Generate redacted A3 Commercial Growth Manifest fixture at `fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json`.
- [x] Document A3 Commercial Growth Manifest in `docs/a3/p3_commercial_growth_manifest_2026_07_09.md`.
- [x] Classify 20+ growth points with A1/A2/A3 evidence bindings, explicit gaps, and API/DB/event/artifact surfaces.
- [x] Add executable Playwright TS E2E coverage for dashboard, report, release evidence, review workflow, SaaS admin, enterprise readiness, and A1/A2 contract visibility.
- [x] Save Playwright dashboard screenshot evidence to `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`.
- [x] Mount the existing A3 API handler into the Playwright E2E server for API-backed dashboard tests.
- [x] Add API-backed Playwright E2E for `source=api-mock`.
- [x] Add hosted report create/revoke Playwright E2E through local A3 API routes.
- [x] Document A3 Commercial Growth Round 3 with 20 growth points and A1/A2 compatibility notes.
- [x] Add Tailwind product-system scaffold with A3 content globs, semantic tokens, PostCSS readiness, documentation, and tests.
- [x] Add React Native / Expo mobile release approval client-surface scaffold, documentation, and tests.
- [x] Add WeChat mini program release approval / incident alert client-surface scaffold, documentation, and tests.
- [x] Reduce commercial CL advisories to 0 while keeping blocker count at 0.
- [x] Add SaaS Admin action guardrail Playwright E2E for local plan-only request recording.
- [x] Add reviewer waiver and approval API-backed Playwright E2E with durable review-record assertions.
- [x] Add hosted report revoked/missing denied-state Playwright E2E with no case-evidence leakage.
- [x] Document A3 Commercial Growth Round 4 review/admin/denied-state evidence and A1/A2 safety boundary.
- [x] Add `a3.billing_usage_summary.v1` to JSON and Markdown report exports.
- [x] Extend `a3.usage_ledger.v1` with read-only plan, quota, billable meter, overage risk, and A1/A2 evidence counts.
- [x] Add `GET /api/a3/billing/readiness` as a read-only billing readiness contract.
- [x] Test billing readiness and usage/billing report exports without enabling real payment mutations.
- [x] Add Growth-Auditor Money-Grade Round 5 artifact with 30+ next commercial growth points.
- [x] Redact Round 4 evidence note identity placeholders so generated A3 docs pass the export firewall.
- [x] Add `a3.commercial_api_contract.v1` with 29 mapped `/v1` SaaS endpoints, A1/A2 owner boundaries, event envelope, usage/audit/RBAC notes, API route, fixture, SQL table, and tests.
- [x] Add A3 commercial OpenAPI 3.1 artifact under `docs/a3/openapi/a3_commercial_api.openapi.json`.
- [x] Add tenant scope helper preserving `organization_id`, `tenant_id`, `workspace_id`, `project_id`, and `environment_id`.
- [x] Add metadata-only `ashr.event_envelope.v1` builder and validation guard for future `event_outbox`.
- [x] Add A1/A2 source artifact hash summaries for A1 RunResult/Trace/ToolCall and A2 GradeResult/ReleaseGate.
- [x] Add `source_artifacts` and `event_outbox` to the A3 SQL migration contract.
- [x] Wire source artifact summaries into API-backed dashboard, release evidence v2, and artifact registry.
- [x] Add A1/A2 live alignment doc for latest `origin/main` and A3 consumption rules.
- [x] Add Growth-Auditor Money-Grade Round 7 artifact with 30 next commercial growth points.
- [x] Verify A3 tenant/event/source-artifact/OpenAPI round with `node --test tests/a3/*.mjs`: 229 pass, 0 fail.
- [x] Verify commercial and hygiene CL guards after tenant/event/source-artifact round.
- [x] Add A3 Auth/RBAC boundary contract with redacted actor context, role policy, and authorization decisions.
- [x] Add local Auth/RBAC API routes: `GET /api/a3/auth/context`, `GET /api/a3/auth/rbac-policy`, `POST /api/a3/auth/authorize`.
- [x] Add Auth/RBAC Boundary panel to SaaS Admin dashboard rendering.
- [x] Add Auth/RBAC boundary summary to SaaS Admin export and Artifact Registry security audit packets.
- [x] Add SQL contract tables for `auth_contexts`, `rbac_policy_snapshots`, and `authz_decisions`.
- [x] Add OpenAPI paths and schemas for Auth/RBAC boundary.
- [x] Verify Auth/RBAC boundary round with focused tests, full A3 Node suite, Playwright E2E, CL commercial/hygiene, and diff check.
- [x] Add A3 slim operating index to reduce future context load and identify done/deferred/next work.
- [x] Add clean-room A3 UI concept preview with four screenshot options before changing the production dashboard style.
- [x] Call the locally configured design LLM with a sanitized prompt and record guidance without exposing keys or private Ashr data.
- [x] Apply the selected Quiet Review Console / Commercial Ledger blend to the production dashboard stylesheet.
- [x] Improve SaaS console visuals for sidebar, topbar, metrics, panels, badges, expected-vs-actual, tool-call diff, media evidence, cloud/admin rows, and failure clusters.
- [x] Fix narrow-screen dashboard overflow by converting the long A3 nav into a horizontal mobile scroller.
- [x] Capture production visual-polish screenshots for desktop and mobile dashboard states.
- [x] Verify the visual-polish round with dashboard/API Node tests, Playwright E2E, commercial CL, hygiene CL, and `git diff --check`.
- [x] Add second-round clean-room visual concepts inspired by current SaaS product directions.
- [x] Apply the stronger Linear / Vercel style release-console direction to the production dashboard.
- [x] Capture V2 concept screenshots and production V2 dashboard desktop/mobile screenshots.
- [x] Keep the second-round visual work limited to A3 dashboard/docs/screenshots without changing A1/A2 semantics.
- [x] Apply V3 colorful, simplified, direct dashboard polish after feedback that V2 still looked too plain.
- [x] Capture V3 production desktop and mobile screenshots.
- [x] Keep V3 visual polish clean-room and preserve A1/A2 dashboard source wiring.
- [x] Replace V3 loud color treatment with a refined V4 premium console style after broader web reference scan.
- [x] Add nav click active-state animation, scroll-aware active nav, section focus animation, and reduced-motion support.
- [x] Fix sticky overview topbar overlap so sidebar anchor navigation does not hide target sections.
- [x] Repair direct hash-link active state so `#console` highlights `Console`.
- [x] Capture V4 production desktop and mobile screenshots and verify mobile width does not overflow.
- [x] Keep V4 UI refinement clean-room and preserve A1/A2 dashboard source wiring.
- [x] Add reviewer denial as the third human review action beside waiver and approval.
- [x] Add `POST /api/a3/review/denials` with local RBAC, idempotency, audit/event-outbox metadata, and SQLite persistence.
- [x] Show dashboard human review action controls and receipt state for waiver, approval, and denial.
- [x] Read usage ledger and billing readiness through A3 API-backed dashboard runtime refresh.
- [x] Surface billing readiness in the SaaS Runtime panel without enabling real payment mutations.
- [x] Add reviewer denial to the commercial API contract, OpenAPI artifact, and redacted contract fixture.
- [x] Preserve existing dry-run/default-safe GitHub Check and PR-comment publishing path without reading tokens or performing live GitHub mutations.
- [x] Confirm shareable report links remain expirable, revocable, and audit-recorded through the existing A3 API/store path.
- [x] Add `apps/dashboard/src/visual-shell.mjs` as a data-driven visual rendering layer for primary navigation, SaaS product surfaces, and detailed workspace rails.
- [x] Reduce the left sidebar to six primary product areas while preserving detailed A3 section access through a horizontal rail.
- [x] Add product-surface navigation for Workspace, Product Console / Onboarding / Audit, SaaS Admin / Login / Team / Trust, Usage, API Keys, and Trust.
- [x] Synchronize active navigation state across sidebar, product surface strip, and workspace rail.
- [x] Rework the dashboard shell into a lighter academic SaaS console style without changing A1 runner or A2 judge semantics.
- [x] Capture V5 visual-rendering screenshots for desktop, mobile, and first-viewport review.
- [x] Verify V5 dashboard wiring with `node --test tests/a3/dashboard_wiring.test.mjs`.
- [x] Convert the left sidebar into accordion groups with subsection links for Overview, Evaluate, Review, Reports, Admin, and Trust.
- [x] Add overview anchors for product surfaces, workspace shortcuts, and run metrics so sidebar subsections target real page areas.
- [x] Fix overview action layout so the data source selector and export buttons do not crowd each other.
- [x] Verify desktop/mobile navigation and button text do not overflow with a Playwright layout probe.
- [x] Wire metadata-only `ashr.event_envelope.v1` rows into A3 report share/view/revoke, admin action, review waiver/approval, and release readback write paths.
- [x] Add local A3 store `eventOutbox` state and expose it through `GET /api/a3/events/outbox`.
- [x] Add dashboard API `event_outbox` summary with event counts, delivery status counts, latest events, and A1/A2 boundary note.
- [x] Add idempotency replay/conflict behavior to A3 mutation-like write paths without storing raw idempotency keys.
- [x] Verify event outbox rows are metadata-only and do not leak raw share tokens, emails, Bearer values, cookies, API keys, or signed URLs.
- [x] Document the A3 event outbox SaaS backbone in `docs/a3/a3_event_outbox_saas_backbone_2026_07_09.md`.
- [x] Enforce fail-closed RBAC on A3 mutation-like API routes before store writes occur.
- [x] Add sanitized `a3.api_authz_denied.v1` denied responses that do not echo request bodies or secret-looking values.
- [x] Add RBAC policies for report view, admin action plan, release readback capture, and event outbox reads.
- [x] Verify unauthorized share/readback/admin/review/revoke/outbox attempts return 403 and do not create extra outbox rows.
- [x] Keep local dashboard demo flows working by sending explicit local role headers from the API client and Playwright tests.
- [x] Document the fail-closed RBAC write-path round in `docs/a3/a3_fail_closed_rbac_write_paths_2026_07_09.md`.
- [x] Add executable A3 schema drift radar for current A1/A2 source schemas with hash-only output.
- [x] Protect `GET /api/a3/a1-a2/schema-drift` behind `audit:read` RBAC.
- [x] Preserve newer G3 A2 evidence-readiness fields for A1 official API readonly, mutating, and paid-media summaries in A3 JSON/Markdown reports.
- [x] Preserve newer A2 result-persistence record fields for `release_unblock_checklist` and `a1_ingestion_digest` without changing A2 judge semantics.
- [x] Extend A3 source-artifact hashing for optional A1/A2 calibration inputs while keeping raw payloads out of reports.
- [x] Verify schema drift and G3 field-preservation round with focused Node tests, full A3 Node tests, E2E, commercial CL, hygiene CL, and diff check.
- [x] Add optional A3 JSON/Markdown consumers for A2 cross-lane security context.
- [x] Add optional A3 JSON/Markdown consumers and source-artifact hashing for A2 SQL store reports.
- [x] Surface the A1/A2 schema drift radar in the dashboard with API-backed and static-safe states.
- [x] Add A3 peer branch calibration for A1/A2 draft PR deltas with API/dashboard/report/source-artifact coverage.
- [x] Add `GET /api/a3/peer-branches/calibration` with redacted downstream-only A1/A2 boundary.
- [x] Add `a3.live_workflow_readiness.v1` for GitHub check publishing, PR comment publishing, review decisions, human operation records, usage/billing reads, and share-link lifecycle.
- [x] Add `GET /api/a3/live-workflow/readiness` and dashboard `Live Workflow Readiness` panel.
- [x] Verify peer branch and live workflow readiness with focused Node tests: 45 pass, 0 fail.
- [x] Add `a3.live_ops_control_plane.v1` for the six requested live SaaS workflow lanes.
- [x] Add `GET /api/a3/live-ops/control-plane` and dashboard `Live Ops Control Plane` panel.
- [x] Keep live ops control plane downstream of A1 hosted workers/billing ledger and A2 judge/release-policy semantics.
- [x] Verify live ops round with focused Node tests: 43 pass, 0 fail.
- [x] Verify full A3 Node suite after live ops round: 254 pass, 0 fail.
- [x] Verify Playwright E2E after live ops round: 9 pass, 0 fail.
- [x] Verify commercial/hygiene CL guards and `git diff --check` after live ops round.
- [ ] Add live GitHub Check and PR comment readback evidence after maintainer-approved integration.
- [ ] Re-run tenant-scope negative tests with real hosted auth/RBAC once A1 auth middleware is available.
- [ ] Add production billing provider checkout/portal only after A1 billing ledger, hosted auth/RBAC, and webhook verification exist.

## Money-Grade Audit Round 2 - 2026-07-09

- [x] Checked branch/status before writing: `codex/a3-commercial-growth-round2...origin/codex/a3-commercial-cl-gate`, clean initial short status.
- [x] Added `docs/a3/p3_growth_auditor_money_grade_round2_2026_07_09.md`.
- [x] Audited current A3 sellable capability against a commercial Ashr++ target.
- [x] Listed 30+ next-round growth points across PR gate, production replay, enterprise audit, self-host, trace ingestion, judge calibration, incident report, review workflow, billing/usage, and API platform.
- [x] Marked which growth points were advanced by the current Playwright, Evidence, and Integration parallel lanes.
- [x] Tagged every growth point for paid willingness, ACV, launch risk, and enterprise/self-host/audit value.
- [x] Captured evidence locations and remaining failure points in the Money-Grade report.
- [x] Kept this round docs-only and did not touch runtime code, tests, fixtures, workflows, secrets, or env files.
- [ ] Live GitHub Check/PR comment/branch-protection readback evidence remains future work.
- [x] Real Playwright TS E2E tooling landed in `playwright.config.ts` and `tests/e2e`.
- [ ] Real hosted auth/RBAC/SSO, production Postgres/RLS, object storage custody, and billing export remain future work.

## P3 Playwright E2E Growth - 2026-07-09

- [x] Added root Playwright package/config so `npm run test:e2e` and `npx playwright test` can execute after dependency install.
- [x] Added local Node static dashboard server under `tests/e2e` without touching A1 runner or A2 judge logic.
- [x] Added TypeScript E2E coverage for the real `apps/dashboard/index.html?source=p3-official-demo` page.
- [x] Covered dashboard metrics, run list, case detail, trace timeline, failure clusters, Product Console, Report Center, Release Evidence, Reviewer Workflow, SaaS Admin, Enterprise Readiness, and raw A2 source switching.
- [x] Verified API/DB/event/artifact, tenant/auth/RBAC/usage/audit, and A1/A2 contract visibility through dashboard UI assertions.
- [x] Confirmed local Playwright Chromium was available for this workstation.
- [x] Verified `npm.cmd run test:e2e`: 4 passed.
- [x] Captured screenshot evidence under `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`.
- [x] Documented PowerShell `.cmd` workaround and browser-install failure mode in `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`.
- [x] Add API-backed `api-mock` E2E with `services/report/a3_api_server.mjs`.
- [x] Add hosted report share/revoke E2E.
- [x] Add admin action guardrail E2E.
- [x] Add reviewer waiver/approval receipt E2E.
- [x] Add revoked/missing hosted report denied-state E2E.

## A3 Live Publish / Review / Billing / Share Closeout - 2026-07-09

- [x] Expose local A3 API routes for GitHub check and PR comment publishing.
- [x] Keep GitHub publish dry-run by default and gate live mode behind hosted session or service account.
- [x] Store sanitized GitHub publish receipts without raw tokens.
- [x] Support reviewer waiver, approval, and denial records.
- [x] Record human operation evidence through review records, SaaS admin requests, audit events, event outbox, and GitHub publish receipts.
- [x] Read usage, billing readiness, and billing migration readiness through API-backed A3 routes.
- [x] Keep billing/admin read-only; no checkout, invoice, subscription, provider webhook, or payment mutation.
- [x] Support report share, view, revoke, expiry, denied access, and audit lifecycle.
- [x] Keep raw share tokens out of persisted docs, fixtures, reports, and API reads.
- [x] Re-verify full A3 Node suite after the closeout: 260 pass, 0 fail.
- [x] Re-verify Playwright E2E after the closeout: 10 pass, 0 fail.
- [ ] Run live GitHub check/comment readback only after maintainer-approved GitHub App or CI integration exists.
- [ ] Replace local store persistence with A1-owned hosted Postgres/RLS once available.
- [ ] Replace read-only billing projections with A1 durable billing ledger and provider webhook evidence before production billing claims.

## A3 Notification Control Plane - 2026-07-09

- [x] Add `a3.notification_control_plane.v1` for Slack, Teams, email, and customer webhook notification readiness.
- [x] Expose `GET /api/a3/notifications/control-plane`.
- [x] Add dashboard `Notification Control Plane` panel and navigation entries.
- [x] Add notification evidence to JSON/Markdown report exports.
- [x] Add `notification_control_plane` artifact and `notification_readiness_packet` to artifact registry.
- [x] Add notification DB migration contract tables for channels, subscriptions, templates, deliveries, and webhook deliveries.
- [x] Add commercial API contract endpoints for notification channels, test planning, and release-gate notification planning.
- [x] Add `notifications:read` RBAC policy coverage.
- [x] Verify notification control plane does not echo Slack, Teams, email, webhook, token, cookie, key, account, or local-path secrets.
- [x] Re-verify full A3 Node suite after notification round: 262 pass, 0 fail.
- [x] Re-verify Playwright E2E after notification round: 10 pass, 0 fail.
- [x] Re-verify commercial CL guard after notification round: passed, 0 blockers, 0 advisories.
- [x] Re-verify hygiene CL guard after notification round: passed.
- [ ] Real Slack/Teams/email/webhook delivery remains future A1 worker work.
- [ ] Real notification payload safety certification remains future A2 redaction/security work.
- [ ] Real notification delivery usage billing remains future A1 usage-ledger work.


## A3 Console Workflow Closure - 2026-07-10

- [x] Notification Control Plane is componentized and no longer rendered as a large inline HTML block.
- [x] Notification Control Plane explains live-ops alignment with reviewer records, billing/usage, and hosted reports.
- [x] Product Console includes an Operations Loop that references reviewer records, hosted reports, and notification lanes.
- [x] Report Center includes a Commercial Loop summary for reviewer records, hosted reports, notification lanes, and audit-backed live-op lanes.
- [x] SaaS Admin includes a Control Summary for release, cloud posture, usage state, team seats, admin requests, and notification lane counts.
- [x] SaaS Admin surfaces Notification Destinations derived from the Notification Control Plane.
- [x] Reviewer Workflow includes Report Share Readiness language linking review records to hosted report sharing state.
- [x] A3 worklog records the GitHub connectivity limitation and the current `spawn EPERM` managed-environment limitation.
- [ ] Re-run dynamic Node tests after managed environment allows test child-process spawning again.
- [ ] Re-run Playwright E2E after managed environment allows the same runtime path.
- [x] Re-sync with GitHub via working `git fetch` transport once `github.com` connectivity returns.
- [ ] Re-verify push / branch publication flow after transport recovery.

- [x] Product Console includes a Go-To-Market section with sellable motion, buyer value, and sales next-step framing.
- [x] SaaS Admin includes Tenant / Environment Control and Release / Rollout Control sections.
- [x] Enterprise Readiness includes an Enterprise Value section mapping current sellable claims and blocked enterprise claims.

- [x] GitHub remote connectivity was re-verified with direct git and GitHub CLI probes.
- [x] Report Center includes a Release Sign-Off summary tile.
- [x] SaaS Admin includes a Billing Account block with plan packaging and invoice-preview posture.
- [x] Enterprise Readiness includes a Self-Host Packet block.

- [x] Reviewer Workflow includes a Review Scope Summary row with release/environment/actor scope metadata.
- [x] SaaS Runtime includes a Burn / Runway section derived from usage-ledger billable units and quota state.

- [x] Billing Account shows plan comparison and invoice-preview-style line items.
- [x] Report Center includes a Sign-Off Detail tile backed by checklist-style release packet data.

- [x] Billing/admin product language prioritizes WeChat Pay and Alipay before secondary international providers.
- [x] SaaS Admin includes a Provider Priority section with WeChat Pay / Alipay before manual invoice and Stripe.
- [x] SaaS Admin includes a Domestic Invoice Workflow shell for procurement-style billing review.
- [x] Billing invoice preview reads as China-first CNY packaging instead of only USD placeholder copy.
- [x] Review workflow data model now exposes approval / waiver / denial trend summary for richer human sign-off surfaces.
- [x] GitHub remote connectivity is currently healthy enough for future A3 publication work (`origin/main` readable, GitHub CLI authenticated).
- [x] Report Center now exposes hosted share-link governance posture for revoke / expiry / blocked states.
- [x] Enterprise Readiness now shows hosted-vs-self-host comparison inside the self-host packet.
- [x] SaaS Runtime now exposes overage alert posture in addition to burn / runway summary.
- [x] Review workflow now exposes release/environment/actor-hash filter options in its contract.
- [x] Dashboard review workflow area now shows filter-preview and decision-trend summaries.
- [x] SaaS Admin now exposes a cloud summary strip for auth, tenant, usage, frontend, and trust posture.
- [x] Review workflow now supports real local filter interaction for release, environment, and actor-hash options.
- [x] Report Center now surfaces share-link governance as a dedicated hosted-report card.
- [x] New review filter controls are styled to match the dashboard control surface.
- [x] Playwright E2E proves review filters, share governance, and cloud summary strip render together in the API-backed dashboard.
- [x] Updated browser screenshot evidence exists for the new review/report/admin cloud-product surfaces.
- [x] Review workflow now shows the currently active filter scope, not only filter controls.
- [x] SaaS Admin control summary now surfaces overage risk earlier in the operator view.
- [x] Review filter state now persists in URL query params and restores on reload.
- [x] Report Center now surfaces a GitHub publish posture card for release-facing reviewer context.
- [ ] Make review filter URL persistence browser-proven, not only source-level and Node-test green.
- [x] Review filter URL sync is now browser-proven in Playwright, not only source-level.
- [x] Full A3 dashboard API-backed Playwright suite is green after reviewer deep-link repair.
- [x] Browser-prove not only URL persistence, but visible scoped reviewer-state persistence after reload.

- [x] SaaS Admin now shows seat / license posture instead of only a raw team roster.
- [x] SaaS Admin now shows API key audit posture, not only key metadata and lifecycle labels.
- [x] SaaS Admin now shows compliance posture tied to trust publishing and audit export constraints.
- [x] SaaS Admin now shows workspace / cloud posture tying environment, usage, billing, and release state together.
- [x] GitHub auth is confirmed healthy; current GitHub risk is transient network reset on fetch, not missing credentials.
- [x] GitHub remote connectivity has recovered enough for `ls-remote` and `fetch --prune` against origin.
- [x] SaaS Admin export now carries seat management, API-key hygiene, usage overage posture, trust compliance posture, and workspace posture.
- [x] Product Console now shows a Commercial Governance Loop tying review, hosted reports, audit events, and readiness together.
- [x] A3 live ops / dashboard / report-builder verification is green after the governance pass (83 pass, 0 fail).
- [x] Live Ops Control Plane now exposes reviewer timeline, GitHub publish timeline, share-link lifecycle, and audit history summaries.
- [x] A3 live ops governance recovery pass is green (`83 pass, 0 fail`).
- [x] Live Ops dashboard now exposes a governance summary strip before the detailed reviewer / GitHub / share-link / audit tables.
- [x] Playwright browser proof covers the new live-ops governance elements in the API-backed dashboard.
- [x] Node + Playwright verification is green after the live-ops governance UX pass (83 pass, 0 fail; Playwright 7 passed).
- [x] Report builder now has a dedicated live-ops governance export summary.
- [x] Live-ops governance export contract test is green (47 pass, 0 fail for the focused report/live-ops suite).- [x] SaaS Admin now shows separation-of-duties commercial controls for release, API-key, and billing/procurement boundaries.
- [x] SaaS Admin now shows workspace/environment control and multi-workspace shell posture instead of only a thin tenant switch line.
- [x] Enterprise Readiness now exposes hosted buyer-readiness comparison rows for procurement/security-facing value explanation.
- [x] Tenant/workspace/separation-of-duties dashboard wiring has dedicated Node test coverage.
- [x] Report Center hosted-report tiles now expose tenant/project scope instead of looking like an unscoped export list.
- [x] SaaS Admin export now preserves richer workspace posture fields for downstream report/export consumers.
- [x] Playwright now proves hosted report scope plus commercial admin/enterprise governance controls render together.
- [x] Report Center tenant scope now preserves tenant/workspace/environment identifiers, not only org/project.
- [x] Hosted report scope in the API-backed dashboard now shows org/workspace/project/environment continuity.
- [x] Node + Playwright both verify the richer environment-aware report scope surface.
- [x] Report Center report rows now preserve row-level workspace/project/environment scope, not only top-level report-center scope.
- [x] Hosted report rows now show workspace/project/environment/share-scope continuity in the API-backed dashboard.
- [x] Node + Playwright both verify row-level report-scope continuity.
- [x] Report Center now exposes export audience governance for internal, reviewer, executive, and blocked customer-external surfaces.
- [x] Dashboard report center now includes an Export Audience tile sourced from the report-center contract.
- [x] Node tests prove export audience governance contract and UI wiring.
- [ ] Re-prove export audience governance in Playwright once the API-backed dashboard startup path is stable again.
- [x] Hosted report rows now display row-level allowed audiences in addition to scope metadata.
- [x] Customer-external export remains explicitly blocked until trust/public export workflow exists.
- [x] Node tests prove row-level audience derivation and dashboard wiring.

- [x] Report Center now exposes audience filters summarizing internal/reviewer/executive/blocked external report posture.
- [x] Report Center now groups hosted reports by workspace and environment for release-governance scanning.
- [x] Report Center now exposes explicit external publish blockers instead of implying future customer export readiness.
- [x] Hosted report rows now show blocked audiences, customer-external blocker posture, release-evidence readiness, and audit visibility.
- [x] Node tests verify audience filters, grouped scope summaries, and external publish blockers contract + dashboard wiring.
- [x] SaaS Admin now exposes explicit Export / Audience Governance for reviewer, executive, and blocked customer-external report posture.
- [x] JSON report exports now include export audience governance summarized from SaaS Admin commercial controls.
- [x] Node tests verify export audience governance flows through SaaS Admin, report builder, and dashboard wiring.
- [x] Enterprise Readiness now distinguishes reviewer, executive, and blocked customer-facing decision packets.
- [x] Enterprise Readiness now explains why customer-facing packet remains blocked even when reviewer/admin shells exist.
- [x] Node tests verify enterprise decision packet wiring in the dashboard.
- [x] Playwright now proves export audience governance surfaces render in the API-backed SaaS Admin console.
- [x] Playwright now proves enterprise reviewer / executive / blocked customer decision packets render in the API-backed console.
- [x] Screenshot evidence exists for export governance plus enterprise decision packets in `docs/screenshots/a3-export-governance-enterprise-packets-api-backed-2026-07-10.png`.
- [x] Live Ops Control Plane now exposes a release publish chain across reviewer records, GitHub publish, hosted reports, usage, and billing surfaces.
- [x] Playwright now proves release publish chain continuity in the API-backed live ops console.
- [x] Screenshot evidence exists for live publish chain continuity in `docs/screenshots/a3-live-publish-chain-api-backed-2026-07-10.png`.
- [x] SaaS Admin Trust Center now explains customer-facing publish blockers and customer-safe artifact posture.
- [x] Playwright now proves trust blockers and customer-safe artifact posture in the API-backed admin console.
- [x] Screenshot evidence exists for trust blockers in `docs/screenshots/a3-trust-blockers-api-backed-2026-07-10.png`.
- [x] Release publish chain now distinguishes waiting-for-approval from denial-blocked states.
- [x] Live Ops Control Plane now exposes reviewer-gate status as an explicit field instead of only counts.
- [x] Live Ops Control Plane now surfaces blocker reasons for governed publish.
- [x] Node tests prove both approval-ready and denial-blocked publish-chain states.
- [x] Playwright regression run still passes after the reviewer-gate publish-blocker change.
- [x] SaaS Admin now exposes commercial ops posture for quote packet, invoice preview, and domestic payment priority.
- [x] SaaS Admin now exposes self-host console posture for enterprise buyer review.
- [x] SaaS Admin now exposes developer-platform posture for SDK/API workflow storytelling.
- [x] API-backed bootstrap now attempts to load report center, artifact registry, product console, review workflow, and SaaS admin during first load.
- [x] Node tests prove the new commercial/self-host/platform shells are wired.
- [ ] Playwright bootstrap still needs a deterministic fix so API-backed pages never stick on `Loading local fixtures...`.
- [x] Root-cause API-backed bootstrap failure to frontend module execution instead of backend payload availability.
- [x] Fix SaaS Admin component syntax so API-backed dashboard modules can execute on first load.
- [x] Re-green critical API-backed Playwright coverage for export governance, live publish chain, and trust blockers.
- [x] Keep commercial/self-host/developer-platform shells intact after bootstrap recovery.
- [x] Confirm direct GitHub remote-read connectivity is intermittently healthy again (`git ls-remote origin HEAD` succeeded).
- [x] SaaS Admin exposes procurement/sign-off posture derived from release-gate and seat state.
- [x] SaaS Admin exposes usage escalation and collections/invoice escalation without enabling live billing mutations.
- [x] SaaS Admin exposes blocked workspace actions with explicit hosted-auth, secret-path, and trust-service dependencies.
- [x] Billing plan/quota normalization no longer lets default empty options shadow calibrated fixture inputs.
- [x] SaaS Admin JSON exports preserve procurement, usage, billing, CN-first provider, and workspace-action readiness fields.
- [x] Node tests prove `team-cn / CNY / over_quota` flows into commercial escalation fields (`100 pass / 0 fail`).
- [x] Playwright proves the new commercial escalation surfaces render in API-backed mode (`3 passed`).
- [x] Screenshot evidence exists at `docs/screenshots/a3-commercial-escalation-console-api-backed-2026-07-10.png`.
- [ ] Split the extremely tall single-page console into route-level or component-level product pages so screenshots and operator scanning become practical.
- [x] Live Ops exposes `a3.commercial_signoff_summary.v1` across reviewer, GitHub, hosted-report, trust, usage, and billing evidence.
- [x] Commercial sign-off distinguishes human denial, incomplete evidence, internal-only readiness, and fully governed readiness.
- [x] Required sign-off roles include reviewer/owner and add billing admin when collections escalation is active.
- [x] Live Ops exports and Markdown reports preserve the commercial sign-off summary and release publish chain.
- [x] API-backed Live Ops renders commercial sign-off evidence and explicit blocker reasons.
- [x] Fix health-tile DOM interpolation so template-rendered panels no longer show `[object HTMLDivElement]`.
- [x] Node regression coverage proves ready, external-blocked, billing-escalated, and human-denial sign-off paths (`101 pass / 0 fail`).
- [x] Playwright proves commercial sign-off, release publish chain, and trust blockers render together (`3 passed`).
- [x] Screenshot evidence exists at `docs/screenshots/a3-commercial-signoff-summary-api-backed-2026-07-10.png`.
- [x] Live Ops rendering is extracted from `app.mjs` into `components/live-ops-control-plane.mjs`.
- [x] The Live Ops component uses DOM nodes and `textContent` rather than `innerHTML`.
- [x] Component wiring tests load the new file directly and preserve release sign-off/A1/A2 contract assertions.
- [x] API-backed Playwright remains green after Live Ops component extraction (`3 passed`).
- [x] Billing Migration Readiness rendering is extracted into `components/billing-migration-readiness-panel.mjs`.
- [x] Live Workflow Readiness rendering is extracted into `components/live-workflow-readiness-panel.mjs`.
- [x] Both readiness components use DOM nodes and `textContent` rather than `innerHTML`.
- [x] Playwright proves Billing Migration, Live Workflow, and release publish-chain continuity after extraction (`3 passed`).
- [x] Screenshot evidence exists at `docs/screenshots/a3-live-workflow-readiness-api-backed-2026-07-10.png`.
- [x] Merge the last locally fetched `origin/main` (`5dbf4ee`) and re-run A1/A2/A3 compatibility checks.
- [x] Contract Radar validates 8 core A1/A2 schemas and 7 public-safe commercial integration domains.
- [x] A1 route/quota, billing, payment, and object-storage evidence is mapped to explicit A3 surfaces.
- [x] A2 security, SQL evaluation-store, and scenario-generation evidence is mapped to explicit A3 surfaces.
- [x] Dashboard shows runtime-to-judge, evidence-to-report, and billing-to-sign-off cross-lane bridges.
- [x] Cross-lane matrix does not embed raw upstream artifacts or mutate A1/A2 semantics.
- [x] SaaS Runtime long contracts are grouped into expandable API, DB, migration, usage, billing, outbox, and guardrail sections.
- [x] Desktop browser measurement keeps SaaS Runtime below 700 px and free of horizontal overflow.
- [x] Mobile Contract Radar uses readable record rows and has no horizontal overflow at 390 x 844.
- [x] Official-demo media rendering no longer throws an undefined `report` error.
- [x] Report Center governance remains visible when hosted report count is zero.
- [x] Full A3 Node suite passes (`286 pass / 0 fail`).
- [x] Full Playwright suite passes (`18 pass / 0 fail`).
- [ ] Continue extracting Report Center and Reviewer Workflow from the remaining 3,853-line `app.mjs`.

## A3 Release Provenance + UI Security Closeout - 2026-07-11

- [x] Re-check `origin/main` and use the latest A1/A2 draft branches only as read-only calibration inputs.
- [x] Extract Report Center into `components/report-center-panel.mjs`.
- [x] Extract Reviewer Workflow into `components/reviewer-workflow-panel.mjs`.
- [x] Reduce `app.mjs` to 3,383 lines without changing A1 runner or A2 judge semantics.
- [x] Keep both extracted components XSS-safe for dynamic values through DOM nodes and `textContent`.
- [x] Build a release-decision provenance graph across A1 run/case/trace/tool-call, A2 grade/failure/release gate, and A3 review/report/usage/billing/audit visibility.
- [x] Keep A2 release gate as the only upstream release-decision authority.
- [x] Fail closed on missing contracts, broken references, tenant-scope mismatch, untrusted identity, RBAC denial, and residual sensitive material.
- [x] Expose provenance in the API-backed dashboard payload, a dedicated read API, and Contract Radar.
- [x] Add metadata-only UI action preflight for reviewer approve/deny/waiver and report create/revoke/export.
- [x] Confirm preflight executes no DB write, cloud write, review decision, report mutation, usage write, or audit persistence.
- [x] Confirm client-declared headers/query values cannot create a trusted hosted identity.
- [x] Complete desktop and 390 x 844 responsive visual inspection with no horizontal overflow.
- [x] Add visual E2E coverage for hierarchy, focus/hover, loading/empty/error states, mobile bounds, and reduced motion.
- [x] Run sanitized real Ashr read-only smoke calibration: 6 of 6 operations succeeded.
- [x] Persist only aggregate redacted Ashr evidence; no key, identity, raw response, signed URL, token, cookie, or email.
- [x] Full A3 Node suite passes (`321 pass / 0 fail`).
- [x] Full Playwright suite passes (`21 pass / 0 fail`).
- [x] TypeScript SDK and real Go HTTP compatibility suite passes (`342 pass / 0 fail`).
- [x] Focused A1/A2 Python compatibility suite passes (`95 pass / 0 fail`, `987 subtests pass`).
- [x] Commercial and hygiene CL guards pass with no findings.
- [x] `.env.local` remains ignored and high-confidence A3 secret scan finds no committed secret.
- [ ] Replace provenance's blocked identity state only after A1 trusted hosted identity verification enters `main` and A3 consumes its authoritative read contract.
- [ ] Execute approved UI mutations only after A1 provides authenticated server-side executors with durable audit/usage writes and A2 verifies current evidence/policy state.
- [ ] Continue route-level web-app decomposition after this closeout; do not re-expand `app.mjs` with new inline panels.

## A1/A2 Evidence Spine + Clean-room Visual Rebuild - 2026-07-11

- [x] Add a public-safe A1 Capture -> A2 Evaluate -> A2 Gate -> A3 Operate evidence contract.
- [x] Preserve A1 runtime/trace/tool-call ownership and A2 judge/failure/release-policy ownership.
- [x] Expose the evidence spine in the API-backed dashboard and a dedicated auditor-protected read endpoint.
- [x] Show A1 identity and A2 multimodal draft deltas as non-authoritative watch signals only.
- [x] Rebuild dashboard HTML/CSS without copying third-party source, assets, fonts, branding, particles, or proprietary implementation.
- [x] Keep six compact top-level navigation groups while retaining links to all existing product surfaces.
- [x] Prevent topbar status/index overlap and desktop/mobile horizontal overflow.
- [x] Keep card radius at or below 8 px, use no gradients, keep letter spacing at zero, and preserve sticky table headers.
- [x] Preserve loading, empty, fail, focus, hover, print, and reduced-motion states.
- [x] Keep SaaS Runtime below 700 px in the tested desktop two-column default state while retaining expandable detail.
- [x] Full A3 Node suite passes (`324 pass / 0 fail`).
- [x] Full Playwright suite passes (`21 pass / 0 fail`).
- [x] Focused A1/A2 Python compatibility passes (`175 pass / 0 fail`, `992 subtests pass`).
- [x] Commercial and hygiene CL guards pass with no findings.
- [x] `.env.local` remains outside the change set and no secret-bearing artifact was added.
- [x] Retry remote sync after the transient network failure and confirm the branch still contains current `origin/main`.
- [ ] Replace draft watch signals only after the A1/A2 contracts merge to `main`.
- [ ] Continue route-level React/Next.js decomposition without weakening the current API and evidence contracts.

## Signal/Form A/B Design + Chinese-First UI - 2026-07-11

- [x] Keep the existing Release Intelligence design as a stable A variant.
- [x] Add an independent Signal/Form B stylesheet without importing A's CSS.
- [x] Keep A and B on the same A1/A2 API, fixture, DOM id, report, and interaction contracts.
- [x] Add an A/B comparison page with split, A-only, and B-only controls.
- [x] Record the supplied archive SHA-256 and MIT/CC0 source boundaries.
- [x] Keep the procedural bitmap local, nonblank, and free of account or secret data.
- [x] Default both variants to Chinese and provide an immediate `中文 / EN` switch.
- [x] Persist language choice while preserving source/design URL state.
- [x] Keep ids, traces, tool-call payloads, scores, failure values, and A2 release authority untranslated and unchanged.
- [x] Browser-prove both variants load the same 32 A1/A2 cases and Evidence Spine.
- [x] Browser-prove desktop and 390 x 844 bounds with no page-level horizontal overflow.
- [x] Save A, B, B-mobile, and A/B comparison screenshots.
- [x] Full A3 Node suite passes (`325 pass / 0 fail`).
- [x] Full Playwright suite passes (`25 pass / 0 fail`).
- [x] Focused A1/A2 compatibility passes (`157 pass / 0 fail`, `987 subtests pass`).
- [x] Commercial and hygiene CL guards pass with no findings.
- [x] High-confidence changed-file secret scan finds no key, token, or private-key material.
- [ ] Continue route-level React/Next.js decomposition after visual selection; do not merge both styles into one growing stylesheet.

## Next.js Route-level Product Webapp - 2026-07-11

- [x] Preserve the legacy dashboard as the full evidence inspector.
- [x] Add a TypeScript + React + Next.js A3 product app.
- [x] Create independent login, overview, projects, runs, case, review, reports, team, billing, and trust routes.
- [x] Consume the existing A3 API instead of duplicating A1/A2 fixtures in page components.
- [x] Keep A1 authoritative for run, trace, observation, and tool-call evidence.
- [x] Keep A2 authoritative for score, pass/fail, failure class, and release decision.
- [x] Default to Chinese and support English without rewriting upstream evidence values.
- [x] Strengthen page title, body, section, metric, and table hierarchy.
- [x] Paginate the 32-case queue at ten rows per page.
- [x] Keep full technical JSON in collapsible evidence sections.
- [x] Add desktop and 390 x 844 responsive layouts without page-level horizontal overflow.
- [x] Keep gradients absent, letter spacing at zero, and radii at or below 8 px.
- [x] Keep hosted auth, reviewer writes, report sharing, key creation, and payment mutations disabled.
- [x] Add source-level A3 webapp contract tests.
- [x] Add route-level Playwright coverage for all pages, navigation, language, pagination, and mobile layout.
- [x] Add a GitHub CL job that typechecks, exports, and browser-tests the webapp.
- [x] Remove the PostCSS audit finding and confirm zero production vulnerabilities.
- [x] Full A3 Node suite passes (329 pass / 0 fail).
- [x] Full Playwright suite passes (30 pass / 0 fail).
- [x] A1/A2 Python contracts pass (571 pass / 5 skipped, 1013 subtests pass).
- [x] Save desktop and mobile screenshot evidence.
- [ ] Replace preview login only after A1 hosted identity/session contracts are authoritative in main.
- [ ] Enable reviewer/report/billing writes only after authenticated API, RBAC, DB, usage, and audit executors exist.

## API Reference + Identity Webapp Integration - 2026-07-11

- [x] Fetch and inspect current main plus latest A1/A2 remote refs before editing.
- [x] Keep A1 OAuth/session/credential/SMTP authority and A2 judge/release authority unchanged.
- [x] Add a Chinese-first `/api-reference` route with English support.
- [x] Cover A1 identity/evidence, A2 judge/release, and A3 console/report endpoints.
- [x] Show implemented, open-draft, and contract-blocked states without overstating readiness.
- [x] Add Google OAuth start adapter with exact `accounts.google.com` validation.
- [x] Add GitHub OAuth start adapter with exact `github.com` validation.
- [x] Never expose or accept provider client secrets in the A3 browser bundle.
- [x] Add email challenge request and verification adapters against actual A1 Go routes.
- [x] Keep email, display name, code, and challenge context out of localStorage and logs.
- [x] Preserve a clearly labeled read-only demo identity path.
- [x] Add an HTML/text verification email handoff without scripts, trackers, or remote assets.
- [x] Document the missing challenge-context blocker as an A3 -> A1 contract change request.
- [x] Keep verification disabled when a server-issued challenge context is unavailable.
- [x] Keep OAuth hosted login incomplete until A1 creates a secure browser session and redirects to an allowlisted Webapp path.
- [x] Pass TypeScript and Next.js static export.
- [x] Pass full A3 Node suite (`334 pass / 0 fail`).
- [x] Pass full Playwright suite (`31 pass / 0 fail`).
- [x] Pass current-main A1/A2 Python contracts (`562 pass / 5 skip`, `1013 subtests pass`).
- [x] Pass commercial CL, hygiene CL, dependency audit, diff check, and high-confidence secret scan.
- [x] Save desktop API/auth/email and mobile API Reference screenshots.
- [x] Consume the implemented A1 account-linking/session/challenge contracts after A1 `c784163` entered `main` `7dd14d7`.
- [ ] Close the browser email-verification flow after A1 delivers mailbox-bound challenge context.
- [ ] Close hosted OAuth login after A1 callback establishes a durable session and performs an exact allowlisted redirect.

## Upstream Identity + Trusted Spine Alignment Patch - 2026-07-11

- [x] Fetch current remote refs and confirm this branch contains `origin/main` `5dbf4ee`.
- [x] Recalibrate against A1 `c784163` and A2 `47c05e5` without merging either draft branch.
- [x] Correct Google/GitHub from initial-login wording to authenticated account linking.
- [x] Keep initial provider login controls disabled instead of presenting a false success path.
- [x] Add explicit A1 capability metadata and a same-origin typed browser-session refresh adapter.
- [x] Never read or persist A1 access or refresh cookie values.
- [x] Add A1 browser-session refresh plus A2 evidence-snapshot/decision-ledger facts to API Reference.
- [x] Preserve A2 as the only grade and release-decision authority.
- [x] Upgrade the public-safe auth fixture to `a3.auth_contract_snapshot.v2`.
- [x] Pass focused A3 auth/reference contract tests (`9 pass / 0 fail`).
- [x] Pass TypeScript typecheck, Next.js production build, and `git diff --check`.
- [x] Record fresh desktop/mobile browser screenshots after the correction.
- [x] Pass full A3, Playwright, A1/A2 peer-contract, CL, dependency, and secret checks.
- [x] Consume these identity and trusted-spine contracts as authoritative after A1 `c784163` and A2 `8cd1d4f` entered `main` `7dd14d7`.

## Merged-main Identity + Trusted Spine Recalibration - 2026-07-12

- [x] Confirm current GitHub `main` is `ccf6ce5` and contains A1 `c784163` plus A2 `8cd1d4f` through integration commit `7dd14d7`.
- [x] Re-read the unified provider-neutral enterprise Release strategy merged in `ccf6ce5`.
- [x] Replace A3 API Reference open-draft labels with merged-main implementation state.
- [x] Keep Google/GitHub initial sign-in unavailable; do not confuse account linking with first login.
- [x] Keep browser email-verification completion blocked until mailbox-bound challenge context exists.
- [x] Upgrade the public-safe auth snapshot to `a3.auth_contract_snapshot.v3`.
- [x] Record A2's required `organization_id`, `tenant_id`, `workspace_id`, `project_id`, and `environment_id` scope.
- [x] Record `scope_complete`, `validation_errors`, direct A1 RunResult validation, and `release_ready=false`.
- [x] Remove the obsolete `a1_auth_not_in_main` blocker.
- [x] Preserve A2 as the only score, failure-class, and release-decision authority.
- [x] Keep key, token, cookie, OTP, email, and account data out of source, fixtures, docs, and screenshots.
- [ ] Add initial Google/GitHub login only after A1 publishes an authenticated callback-to-Webapp session flow.
- [ ] Enable browser verification completion only after A1 publishes mailbox-bound challenge context and registration session handoff.

## Release Delivery Golden Path - 2026-07-12

- [x] Re-read the latest known main strategy and current A1/A2 contracts before editing A3.
- [x] Generate a fresh A1 TypeScript RunResult instead of reusing run `11926`.
- [x] Feed the exact new A1 cases through the existing A2 internal judge service.
- [x] Preserve A2 score, pass/fail, failure class, and Trusted Spine release authority.
- [x] Prove that A1 execution success can coexist with A2 evaluation failure.
- [x] Include the media-pipeline scenario `A2-S031` in the new run.
- [x] Add an A2 judge-service wrapper adapter to Gate CLI without changing A2 semantics.
- [x] Add the A2 Trusted Spine as an authority record in the run-specific Audit Bundle.
- [x] Verify the new Audit Bundle root, 14 artifacts, and 7 custody events.
- [x] Verify the signed archive root, signature, and 15 entries.
- [x] Add a versioned `a3.release_artifact_manifest.v1` and verifier.
- [x] Add a 16-check `a3.deployment_acceptance.v1` that fails closed.
- [x] Add an 11-stage `a3.delivery_golden_path.v1` that does not overstate readiness.
- [x] Reject contract-only GitHub receipts as live production evidence.
- [x] Add read-only GitHub Check, PR comment, and required-check observation CLI.
- [x] Add a Next.js `/delivery` page and `a3-golden-path` data source.
- [x] Add CI generation and GitHub Actions artifact upload for `0.2.0-rc.1`.
- [x] Add release notes, implementation docs, and a 30-point growth audit.
- [x] Pass final A3 Node (`406/406`) and A2 (`186/186`, `1050` subtests) contract suites.
- [x] Pass Next.js typecheck/build (15 pages) and route-level Playwright (`11/11`).
- [x] Pass CL, dependency audit, YAML/JSON, secret/path, and diff hygiene checks.
- [x] Record Docker/PostgreSQL, Go, and Cargo-dependent A1 checks as local environment gaps without changing upstream tests.
- [x] Produce and download a real GitHub Actions release-candidate artifact for commit `01f8707`.
- [x] Separate candidate-head SHA from the CI-tested pull-request merge SHA.
- [x] Attach a real GitHub Check readback for candidate `ad6113e`.
- [x] Publish and read back a real operator PR comment for candidate `ad6113e`.
- [x] Download and verify the real versioned GitHub Actions artifact receipt.
- [x] Make CI independently verify and upload the sealed candidate packet instead of regenerating a different head-bound packet.
- [x] Normalize generated evidence to LF and prove the sealed packet is byte-stable across Windows and Linux.
- [ ] Install and prove a tenant-bound custom GitHub App.
- [ ] Enable branch protection and prove the required check is enforced.
- [ ] Attach a deployed staging/VPC acceptance receipt.
- [ ] Obtain a new A2 `allow` Decision Ledger record before any production release.

## Golden Agent Tool-chain Repair - 2026-07-12

- [x] Re-fetch current `origin/main` and inspect current A1/A2 peer refs without treating draft contracts as authoritative.
- [x] Preserve the sealed `0.2.0-rc.1` directory instead of overwriting historical evidence.
- [x] Add an A3-owned deterministic, local-only, read-only Golden Agent.
- [x] Execute `web.search` against the A2 official-price fixture.
- [x] Execute `media.fetch` → `image.view` → `media.classify` in the A2-required order.
- [x] Validate PNG signature, dimensions, provenance path, and SHA-256 before classification.
- [x] Fail closed when evidence is missing, malformed, or outside the versioned case set.
- [x] Run the unchanged A1 TypeScript Runner and record 3/3 execution, 100% Trace completeness, and 4 Tool Calls.
- [x] Run the unchanged A2 Judge and record 3/3 grades, score 100, and failure class `none`.
- [x] Recompute the A2 response a second time and prove byte-identical SHA-256 output after LF normalization.
- [x] Preserve the merged-main A2 Trusted Spine `block`; do not synthesize A2 `allow` in A3.
- [x] Build and verify an independent rc.2 Audit Bundle and custody chain.
- [x] Build and verify an independent rc.2 signed archive.
- [x] Build a blocked `0.2.0-rc.2` Release Artifact with `production_release=false`.
- [x] Keep `ci_tested_sha_alias=null` until real CI evidence exists.
- [x] Hash release documentation into the Release Artifact manifest.
- [x] Add `a3-golden-path-rc2` to Store, API, and Next.js source selection.
- [x] Show A1 execution, A2 grades, Trace completeness, Tool Calls, and Decision Ledger as separate evidence.
- [x] Use A1 aggregate Tool Call count instead of double-counting normalized calls.
- [x] Add desktop and 390 x 844 Playwright evidence without overflow.
- [x] Capture final-frame screenshots with animations disabled.
- [x] Push the rc.2 evidence commit and attach live GitHub Actions Check, operator PR comment, and Actions artifact readbacks.
- [x] Download the rc.2 Actions artifact and prove its ZIP digest and all 19 uploaded file hashes match GitHub and the committed snapshot.
- [x] Record that the Check is owned by the GitHub Actions App and the comment by operator OAuth; neither proves a tenant custom GitHub App.
- [x] Read main branch protection and preserve the real `404` / `enforced=false` result instead of claiming a required check.
- [ ] Obtain an A2 Decision Ledger record tied to `a3-golden-20260712-002`.
- [ ] Install a tenant GitHub App, enable required branch protection, and attach deployed staging evidence.

## GitHub Readback Product Surface - 2026-07-12

- [x] Load rc.1 and rc.2 Check, comment, required-check, and Actions-artifact receipts through the source configuration.
- [x] Preserve those receipts as first-class Store snapshot and Dashboard API fields.
- [x] Render four Chinese-first, bilingual GitHub readback cards on the Delivery route.
- [x] Distinguish GitHub Actions App, operator OAuth, tenant App, A2 authority, and branch-policy enforcement.
- [x] Restrict rendered evidence links to HTTPS `github.com` URLs.
- [x] Show the real main policy result as HTTP 404 and `not enforced`.
- [x] Keep A2 `block`, Golden Path 7/11, Deployment Acceptance 8/17, and production false unchanged.
- [x] Add desktop and 390 x 844 readback screenshots with no horizontal overflow.
- [x] Leave the sealed rc.2 release documentation and manifest unchanged; record this as a post-seal UI increment.

## rc.1 vs rc.2 Release Comparison - 2026-07-12

- [x] Compare the exact rc.1 and rc.2 A1/A2 evidence instead of relying on release-note prose.
- [x] Show that A1 execution remained 3/3 while A2 evaluation improved from 1/3 to 3/3.
- [x] Show Tool Calls `0 -> 4` and `missing_required_tool` `2 -> 0`.
- [x] Show Release Artifact entries `12 -> 16`.
- [x] Keep Golden Path `7/11` and Deployment Acceptance `8/17` unchanged.
- [x] Keep A2 Decision Ledger `block`, `release_ready=false`, and production false unchanged.
- [x] Expose `a3.release_comparison.v1` through Store, Dashboard API, API Reference, and OpenAPI.
- [x] Record that A3 did not recompute A1 execution, A2 score, pass/fail, failure class, or release decision.
- [x] Add Chinese-first and English UI with clear visual hierarchy and raw evidence access.
- [x] Pass focused Node, TypeScript, production build, OpenAPI, and Playwright checks.
- [x] Pass final A3 Node `419/419`, current-main A2 `186/186` plus `1050` subtests, and full Playwright `37/37`.
- [x] Pass both CL guards and reverify the sealed rc.2 manifest without changing it.
- [x] Save desktop and 390 x 844 screenshots with no horizontal overflow.
- [x] Do not rewrite any sealed rc.2 manifest input.

## Candidate Integrity and Deployment Handoff - 2026-07-13

- [x] Revalidate the current A2 Trusted Spine through the backend verifier.
- [x] Show `integrity_invalid` instead of treating the sealed historical `block` as current authority.
- [x] Fail current `upstream_decision` closed to `unknown` when integrity is invalid.
- [x] Preserve the sealed rc.2 historical decision separately.
- [x] Compare expected A3 run/scope with observed A2 evidence and decision run/scope.
- [x] Check Release Artifact and Golden Path run binding.
- [x] Add `a3.deployment_handoff.v1` with 17 checks and 5 owner groups.
- [x] Expose all 9 blocking checks with next action and required receipt.
- [x] Keep A3 product-evidence ownership at 6/6 without overstating the other owner groups.
- [x] Expose Deployment Handoff and runtime authority through Store, API Reference, and OpenAPI.
- [x] Add Node tests for fail-closed mismatch and a fully bound ready handoff.
- [x] Add Chinese/English UI and desktop/mobile Playwright assertions.
- [x] Save four candidate-binding and deployment-handoff screenshots.
- [x] Record at least 20 actionable Growth Auditor points.
- [x] Keep A1 runtime facts and A2 score/pass/fail/failure-class/release semantics unchanged.
- [x] Keep keys, tokens, cookies, email, OTP, signed URLs, local paths, and customer data out of artifacts.
- [ ] Obtain a new A2 Trusted Spine for `a3-golden-20260712-002` and the exact five-level scope.
- [ ] Rebuild a single-candidate Release Artifact after A2 supplies that authoritative record.
- [ ] Attach tenant GitHub App, main required-check, staging/VPC, PostgreSQL/RLS, queue, object-storage, and rollback receipts.

## Deployment Receipt Inbox - 2026-07-13

- [x] Add `a3.deployment_receipt.v1` and `a3.deployment_receipt_inbox.v1`.
- [x] Bind submissions to the current blocker, candidate, A1 run, source, and five-level tenant scope.
- [x] Reject secrets, tokens, cookies, emails, signed URLs, local paths, unsafe refs, invalid hashes, and unknown selectors.
- [x] Require `Idempotency-Key` for submit and review mutations.
- [x] Require `expected_version` and return HTTP 409 for stale reviewer writes.
- [x] Support acknowledge, reject, and supersede metadata states.
- [x] Keep `submitted` and `acknowledged` non-authoritative.
- [x] Keep Deployment Acceptance at 8/17 and `production_verified_count=0`.
- [x] Keep current A2 authority `integrity_invalid` / `unknown` and historical sealed `block` separate.
- [x] Emit metadata-only audit and event-outbox records for every successful mutation.
- [x] Persist receipt state through SQLite restart with a dedicated migration/table.
- [x] Add separate read, submit, and review RBAC permissions.
- [x] Add three protected HTTP routes and browser-safe same-origin calls.
- [x] Add OpenAPI, API Reference, DB contract, and commercial contract coverage.
- [x] Add Chinese-first and English UI with all expected operation states.
- [x] Pass focused workflow, Store, API, concurrency, security, and SQLite tests.
- [x] Pass a browser submit/conflict/denied/reviewer-acknowledge workflow.
- [x] Save and inspect desktop and 390 x 844 screenshots without document overflow.
- [x] Pass final A3 Node `429/429`, current-main A2 `186/186` plus `1050` subtests, Next.js typecheck/build, Playwright `38/38`, both CL guards, and both npm production audits.
- [x] Reverify the sealed rc.2 bundle, signed archive, and Release Artifact without changing their inputs.
- [x] Add server-only authoritative verifier readback before any receipt can become production verified.
- [ ] Obtain the nine real external receipts; the inbox itself does not close those blockers.

## Authoritative Deployment Receipt Verifier - 2026-07-13

- [x] Add `a3.deployment_receipt_authoritative_readback.v1` and `a3.deployment_acceptance_projection.v1`.
- [x] Restrict verification to A1-verified hosted `service_account` principals with `deployment:verify`.
- [x] Reject demo/header-forged service accounts and every client-supplied verification result field.
- [x] Invoke the injected resolver only after auth, tenant scope, receipt state, version, and idempotency checks.
- [x] Bind readbacks to receipt, blocker, candidate, A1 run, five-level scope, evidence SHA-256, verifier class, and authority.
- [x] Require every blocker-specific claim to be present, boolean, and true for `verified` status.
- [x] Persist trusted rejections without promoting production state.
- [x] Store immutable sequence and previous-readback hashes in migration `018_deployment_receipt_readbacks`.
- [x] Prove idempotent replay does not invoke the resolver twice.
- [x] Emit sanitized audit, event-outbox, and usage-meter records.
- [x] Restore authoritative readbacks through SQLite restart.
- [x] Keep source Deployment Acceptance unchanged and expose only a rebuild-required projection.
- [x] Keep A2 score, pass/fail, failure class, Decision Ledger, and Release Ready unchanged.
- [x] Add OpenAPI/API Reference/commercial contract coverage with runtime parity `57/57`.
- [x] Display server readback and source-vs-projected acceptance in the Delivery page.
- [x] Prove the browser UI exposes no internal verifier call or verification button.
- [x] Keep the default rc.2 source at `8/17 -> 8/17` with zero real production readbacks.
- [x] Leave sealed rc.2 bundle, archive, manifest, and authority records unchanged.
- [x] Pass A3 Node `436/436` and current-main A2 `186/186` plus `1050` subtests.
- [x] Pass Next.js typecheck/build with 15 static pages and Playwright `38/38` plus the strengthened focused E2E `1/1`.
- [x] Pass CL hygiene, Commercial CL, both production npm audits, and `git diff --check`.
- [x] Reverify rc.2 bundle `15/15`, custody `7/7`, archive `16/16`, Ed25519 signature, and Release manifest without rewriting sealed inputs.
- [x] Connect the GitHub App and required-check resolver classes to live read-only GitHub API state.
- [x] Preserve installation HTTP 401, main policy HTTP 404, and `github-actions` identity as trusted rejection evidence.
- [x] Prove the internal HTTP verify route persists the rejected readback without changing `8/17` or production receipt count `0`.
- [x] Pass final A3 `449/449`, A2 `186/186` plus `1050` subtests, Next.js build, Playwright, CL, audits, and sealed rc.2 verification.
- [ ] Connect all nine resolver classes to real external services and collect real receipts.
- [ ] Obtain an A1 tenant-installation binding receipt and a Check published by the tenant custom GitHub App.
- [ ] Obtain maintainer-approved main policy and failing-merge denial receipts.
- [ ] Rebuild and reseal Deployment Acceptance only after same-candidate A1/A2/A3 evidence exists.

## A1-backed Self-host Sandbox Calibration - 2026-07-13

- [x] Execute A1 local control-plane health behavior and preserve `local_only=true`.
- [x] Execute A1 worker enqueue, lease, heartbeat, retry, and dead-letter behavior.
- [x] Execute A1 expired-lease recovery with a second worker identity alias.
- [x] Execute A1 local object write/readback and a tamper-negative checksum test.
- [x] Invoke Python without a shell, with an allowlisted environment, timeout, and output limit.
- [x] Reject invalid schema, missing checks, production overclaims, and A2 authority overclaims.
- [x] Reject token, email, cookie, signed URL, API-key-like value, and absolute local path leaks.
- [x] Generate a sanitized SHA-256-bound calibration fixture.
- [x] Add a tenant-scoped Memory/File/SQLite Store resource.
- [x] Add migration `019_self_host_sandbox_calibrations` with all production mutation flags false.
- [x] Add `GET /api/a3/deployment/sandbox-calibration` with `deployment:read`.
- [x] Audit hosted allow/deny reads and reject cross-scope access.
- [x] Add OpenAPI, commercial API contract, DB contract, and API Reference coverage.
- [x] Add Chinese-first and English Delivery UI.
- [x] Cover loading, ready, partial, empty, failed, denied, and retry states.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, and production receipts `0` unchanged.
- [x] Keep current authority `integrity_invalid`, current A2 decision `unknown`, and historical A2 `block` unchanged.
- [x] Save and inspect desktop and 390 x 844 screenshots without document-level overflow.
- [x] Add more than 20 executable next growth points in Growth Auditor Round 18.
- [x] Leave the sealed rc.2 bundle, archive, manifest, and hashed inputs unchanged.
- [x] Pass final A3 Node `458/458` and current-main A2 `186/186` plus `1050` subtests.
- [x] Pass Next.js typecheck/build with 15 static pages and full Playwright `40/40`.
- [x] Pass both CL guards, both production npm audits, export safety checks, and diff hygiene.
- [x] Reverify rc.2 bundle `15/15`, custody `7/7`, archive `16/16`, and Release manifest hash without rewriting sealed inputs.
- [ ] Run PostgreSQL/RLS, container identity, VPC policy, and upgrade/rollback in a target environment.
- [ ] Obtain a same-candidate A2 Trusted Spine before rebuilding production acceptance.

## Live Local PostgreSQL RLS Qualification - 2026-07-13

- [x] Locate and use a real PostgreSQL 17.9 engine without modifying the user's existing database authentication.
- [x] Start an isolated loopback-only PostgreSQL test instance and keep it separate from the installed service data.
- [x] Keep published migration 019 unchanged and add migration 020 for the five-level composite key, scope digest, and RLS upgrade.
- [x] Enable and force PostgreSQL RLS on `self_host_sandbox_calibrations`.
- [x] Require exact organization, tenant, workspace, project, and environment settings in `USING` and `WITH CHECK`.
- [x] Keep SQLite free of PostgreSQL-only policy syntax and label it as a reference store.
- [x] Apply the migration 019-to-020 chain twice against PostgreSQL and prove idempotency.
- [x] Use a `NOSUPERUSER NOBYPASSRLS` runtime role for isolation checks.
- [x] Prove same-scope read returns one row and same-scope write succeeds.
- [x] Prove cross-scope read returns zero rows and cross-scope write is rejected by RLS.
- [x] Prove missing-scope read returns zero rows.
- [x] Remove all probe rows and the temporary role, then independently verify cleanup.
- [x] Add a no-shell, timeout-bound, output-limited `psql` probe.
- [x] Reject CLI password/DSN arguments and accept passwords only through environment variables.
- [x] Save a credential-free `a3.postgres_rls_qualification.v1` fixture.
- [x] Attach the qualification to the existing self-host Store/API/SQLite payload.
- [x] Extend OpenAPI and API Reference without adding an unprotected route.
- [x] Add a Chinese-first PostgreSQL qualification module to the Delivery page.
- [x] Keep `production_verified=false`, target-customer verification false, Deployment Acceptance `8/17`, and A2 authority unchanged.
- [x] Add desktop/mobile browser assertions and a focused mobile database screenshot.
- [x] Add Growth Auditor Round 19 with at least 20 executable next steps.
- [x] Pass A3 Node `463` runnable tests with one explicit target-PostgreSQL opt-in skip.
- [x] Pass current-main A2 `186/186` plus `1050` subtests and A3 Python `2/2` outside the restricted temp boundary.
- [x] Pass Next.js typecheck/build with 15 static pages and full Playwright `40/40`.
- [x] Pass OpenAPI runtime parity `58/58`, both CL guards, both production npm audits, export safety, and diff hygiene.
- [x] Reverify sealed rc.2 Bundle `15/15`, custody `7/7`, archive `16/16`, and Release Artifact without rewriting inputs.
- [x] Re-fetch `main`/A1/A2 and inspect A2 `b778e11` additive multimodal receipts without treating `qualified_for_review` as PASS or release authority.
- [ ] Run the same probe through an A1-authenticated service identity in authorized staging/VPC PostgreSQL.
- [ ] Prove connection-pool scope reset, migration rollback, backup, PITR, and restore in the target environment.
## WeChat Enterprise Release Center - 2026-07-13

- [x] Replace the two-page static shell with four product pages.
- [x] Add 发布工作台、发布审批、风险告警、账户与连接.
- [x] Use Chinese-first customer terminology without visible A1/A2/A3 lane badges in WXML.
- [x] Keep A1 RunResult/Trace/ToolCall and A2 GradeResult/ReleaseGate/DecisionLedger as internal provenance only.
- [x] Add explicit `preview` and `connected` modes.
- [x] Require an HTTPS API base and allowlist every client route.
- [x] Reject secret-bearing request and response material.
- [x] Prohibit token, cookie, API-key, Authorization-header, localStorage, sessionStorage, and `wx.setStorage` credential persistence.
- [x] Map `/api/a3/health` `ok: true` correctly.
- [x] Map Dashboard evidence stages to execution evidence, evaluation result, release decision, and human review.
- [x] Map Release Evidence v2 source-artifact hashes into preflight evidence references.
- [x] Keep approve/deny operations at `preflight_only`; do not write a release decision.
- [x] Add loading, partial, empty, error, retry, and pull-to-refresh states.
- [x] Add alert filtering, selected incident detail, timeline, evidence status, and response checklist.
- [x] Add account/API connectivity and production-capability diagnostics.
- [x] Keep `touristappid` and label unsupported production capabilities honestly.
- [x] Remove prominent lane badges from the Webapp brand and primary product navigation.
- [x] Translate remaining customer-visible loading, identity-error, and API Reference lane names into enterprise product terminology.
- [x] Add and visually inspect four 390 x 844 mini-program preview screenshots.
- [x] Pass focused mini-program contract/security tests `10/10`.
- [x] Pass full A3 Node regression with `468` passes, `1` explicit live-target skip, and `0` failures.
- [x] Pass full Playwright `41/41` and Next.js 15-page production build.
- [x] Pass CL hygiene, Commercial CL, diff hygiene, and changed-product-file secret scan.
- [ ] Compile and inspect all pages in WeChat Developer Tools with a qualified production AppID.
- [ ] Connect a production identity backend and server-issued WeChat session.
- [ ] Add audited review mutation only after hosted auth, RBAC, idempotency, and immutable audit persistence are proven.
- [ ] Obtain real subscription-message, upload, review, and publication receipts.

## Multimodal Disagreement Review Queue - 2026-07-14

- [x] Re-fetch main, A1, and A2 before implementation.
- [x] Inspect A2 multimodal changes through peer ref `564d4b0` without merging the peer branch.
- [x] Preserve support for `a2.multimodal_cross_provider_comparison.v1`.
- [x] Add support for `a2.multimodal_cross_provider_comparison.v3` repeats and aggregates.
- [x] Use a real A2 `public_safe=true`, `release_authority=false` v3 artifact.
- [x] Reject raw payloads, URLs, secrets, account paths, and forged release authority.
- [x] Require exact five-level tenant scope on import and read.
- [x] Verify summary counts, repeat identity, aggregate instability, and receipt conservation.
- [x] Require `Idempotency-Key` and preserve duplicate replay behavior.
- [x] Add protected import and reviewer queue routes with separate RBAC permissions.
- [x] Return cross-tenant 404 without model, case, or hash leakage.
- [x] Emit metadata-only audit and event-outbox evidence.
- [x] Persist the comparison through Memory, JSON-file, and SQLite stores.
- [x] Add queue evidence to Dashboard, JSON, Markdown, and shareable reports.
- [x] Keep export redaction and share-token safety intact.
- [x] Add API Reference v9 and preserve OpenAPI runtime parity `60/60`.
- [x] Add Chinese-first repeat, aggregate, risk, queue, and capability labels.
- [x] Keep customer-facing UI free of prominent A1/A2/A3 lane badges.
- [x] Save and inspect desktop and 390 x 844 screenshots without overflow.
- [x] Pass A3 Node `476` runnable tests plus one explicit live-target skip.
- [x] Pass current-main A2 `186/186`, Next.js 15-page build, and Playwright `42/42`.
- [x] Pass both CL guards, both production npm audits, and diff hygiene.
- [x] Add implementation evidence and Growth Auditor Round 20 with 24 executable next steps.
- [x] Keep release authority, score, pass/fail, failure class, and Decision Ledger unchanged.
- [x] Add three-way v2 after A2 Round 50 published an exact public-safe runtime artifact; consume a documented redacted representative projection.
- [ ] Add four-way v1 only after an exact public-safe runtime artifact exists.
- [ ] Ingest an authoritative real-review receipt and same-candidate A2 Decision Ledger.
- [ ] Run the workflow in authorized staging with target PostgreSQL/object custody and production identity.

## Multimodal Reviewer Assignment and Lease Workflow - 2026-07-14

- [x] Re-fetch and inspect current main, A1, and latest A2 peer state before implementation.
- [x] Record A2 Round 49 real provider counts, quality, latency, usage and blockers in a redacted A3 calibration fixture.
- [x] Confirm no public-safe real human-review receipt exists and refuse to fabricate one.
- [x] Add claim, renew, release, transfer, expiry and reclaim transitions.
- [x] Add append-only assignment events and `expected_version` optimistic concurrency.
- [x] Require header-only `Idempotency-Key` and preserve duplicate replay behavior.
- [x] Derive actor hash and role from the authorization context instead of assignment payload fields.
- [x] Reject disposition, score, risk and release-authority fields at the assignment boundary.
- [x] Add protected assignment API with `release:review` RBAC.
- [x] Enforce five-level tenant scope and cross-tenant 404 behavior.
- [x] Emit metadata-only audit, event outbox and usage-meter records.
- [x] Persist and reopen assignment state through Memory, JSON file and SQLite stores.
- [x] Add SQL migrations 021/022 and PostgreSQL forced-RLS contract coverage.
- [x] Add current assignment state to Dashboard, JSON, Markdown and Hosted Report exports.
- [x] Add OpenAPI typed request/receipt/concurrency schemas and runtime route parity.
- [x] Add API Reference v10 and commercial API/DB contract coverage.
- [x] Add Chinese-first active, unassigned, expired, reviewer alias, version and lease UI states.
- [x] Add focused transition, conflict, security, API and persistence tests.
- [x] Pass final A3 Node `479` runnable tests with one explicit live-target PostgreSQL skip and zero failures.
- [x] Pass current-main A2 `186/186`, Next.js 15-page typecheck/build, Playwright `42/42`, and OpenAPI runtime parity `61/61`.
- [x] Pass both CL guards and both production npm audits with zero findings, blockers, advisories, or vulnerabilities.
- [x] Save and inspect desktop and 390 x 844 review-queue screenshots without document-level horizontal overflow.
- [x] Keep `.env.local` ignored and exclude keys, tokens, cookies, identities, signed URLs, raw provider payloads, and private media.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [ ] Ingest a real A2 human-review receipt and verify its chain.
- [ ] Bind the terminal review hash to a same-candidate A2 Decision Ledger.
- [ ] Run the workflow with A1 hosted identity, CSRF, target PostgreSQL RLS and staging acceptance evidence.

## Signed Multimodal Review Assignment Packet - 2026-07-14

- [x] Re-fetch and inspect current main, A1, A2 and the enterprise strategy before implementation.
- [x] Preserve A2 disposition and release authority and refuse to fabricate a real human-review receipt.
- [x] Recompute every assignment event id/hash and reject unknown or unsafe event fields.
- [x] Validate contiguous versions, reviewer transitions, monotonic time, tenant scope and queue/case/comparison binding.
- [x] Add a metadata-only packet root hash and fail-closed packet verifier.
- [x] Reject secret, email, URL, local account path, raw identity, raw model payload, private media and signed URL material.
- [x] Add a packet build/verify CLI with JSON and Markdown output.
- [x] Add Gate CLI `--multimodal-review-packet` verified ingestion as a `review_record`.
- [x] Add a new Audit Bundle without rewriting the historical rc.2 bundle.
- [x] Add a locally Ed25519-signed Audit Archive and verify packet, bundle, custody, archive root and signature.
- [x] Label the signer `self_signed_local_key_not_sso_bound` and avoid any production-signing claim.
- [x] Add packet state and metadata-only assignment history to Dashboard and report exports.
- [x] Add the packet to Artifact Registry with content hash, missing production-signature controls and a packet preset.
- [x] Upgrade API Reference to v11 and update the commercial API contract fixture/documentation.
- [x] Add Chinese-first integrity/signature UI and keyboard-expandable history.
- [x] Make Playwright claim through the protected API before checking the rendered history.
- [x] Save and inspect desktop and 390 x 844 screenshots without document-level horizontal overflow.
- [x] Add positive, tamper, scope, CLI, bundle, archive, API, report and registry tests.
- [x] Add implementation evidence and Growth Auditor Round 22 with 22 executable next steps.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [x] Pass A3 Node `486` runnable tests with one explicit live-target PostgreSQL skip and zero failures.
- [x] Pass current-main A2 `186/186` test files and `1050` subtests without changing A2 judgement semantics.
- [x] Pass Next.js TypeScript/build with 15 pages and full Playwright `42/42`.
- [x] Pass CL hygiene with zero findings and Commercial CL with zero blockers/advisories.
- [x] Confirm root and Webapp production dependency audits report zero vulnerabilities.
- [x] Verify the packet, all `3/3` Audit Bundle artifacts and custody chain, and the Audit Archive root and Ed25519 signature.
- [ ] Import and validate a public-safe real A2 human-review chain.
- [ ] Bind the terminal review hash and packet to a same-candidate A2 Decision Ledger.
- [ ] Replace local self-signing with tenant-bound KMS/HSM or workload identity in authorized staging.

## A2 Round 50 Three-provider Review Intake - 2026-07-14

- [x] Confirm remote main `ccf6ce5`, A1 peer `770ccc8`, A2 peer `bb3bcfe`, PR state and CI through authenticated GitHub API after Git transport stalled.
- [x] Re-read the enterprise strategy and preserve A1 identity/A2 decision ownership.
- [x] Inspect the exact A2 three-way v2 schema, 74-case artifact, queue receipt, review conservation and shared-candidate blocker evidence.
- [x] Record that Round 50 has one pending review and zero real human-review receipts.
- [x] Add a three-case public-safe projection preserving the real representative rows, evidence hashes and queue receipt.
- [x] Document that the projection is not byte-identical to the full 74-case artifact.
- [x] Validate the adapter against the complete 74-case upstream artifact with zero errors, then remove the temporary copy.
- [x] Add strict top-level and nested field allowlists for three-way v2.
- [x] Require exactly three matching provider-key sets across evidence, journals and case observations.
- [x] Recompute eligible counts, comparison states, four-way summary and three pairwise summaries for integrity only.
- [x] Enforce queue-receipt conservation and comparison-artifact/case/artifact/repeat binding.
- [x] Reject raw payloads, secrets, URLs, email, signed URLs, unsafe paths and release authority.
- [x] Add `p3-a2-round50` to fixture Store, API server, Next.js selector and legacy compatibility selector.
- [x] Preserve Memory, JSON-file and SQLite generic snapshot compatibility.
- [x] Prove SQLite restart restores the three-way comparison and assignment lease.
- [x] Extend OpenAPI with the exact three-way v2 envelope and keep runtime parity `61/61`.
- [x] Upgrade API Reference to v12 with A1 `770ccc8` and A2 `bb3bcfe` peer calibration.
- [x] Extend JSON, Markdown and Hosted Report exports with provider-set and provider-observation fields.
- [x] Render a dynamic three-provider Review UI without inventing provider/model identity.
- [x] Preserve assignment packet integrity and all A2 release-authority boundaries.
- [x] Add unit, tamper, API, assignment, SQLite, OpenAPI, report and browser coverage.
- [x] Save and inspect desktop and 390 x 844 screenshots without document-level horizontal overflow.
- [x] Add implementation evidence and Growth Auditor Round 23 with 23 executable next steps.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [x] Pass A3 Node `489` runnable tests with one explicit live-target PostgreSQL skip and zero failures.
- [x] Pass current-main A2 `186/186` test files and `1050` subtests without changing A2 judgement semantics.
- [x] Pass Next.js TypeScript/build with 15 pages and full Playwright `43/43`.
- [x] Pass OpenAPI runtime parity `61/61`, CL hygiene with zero findings, and Commercial CL with zero blockers/advisories.
- [x] Confirm root and Webapp production dependency audits report zero vulnerabilities.
- [x] Keep `.env.local` ignored and exclude credentials, account identity, signed URLs, raw provider payloads and private media.
- [ ] Import and validate a real A2 human-review chain.
- [ ] Bind the review result and three-way evidence to one exact shared candidate and Decision Ledger.
- [ ] Run the workflow with hosted identity, target PostgreSQL RLS, object storage and tenant KMS in authorized staging.

## Multimodal Review Evidence Request Workflow - 2026-07-14

- [x] Re-read the enterprise strategy and calibrate against main `ccf6ce5`, A1 peer `6a985b8`, and latest A2 peer `7504680` while retaining exact Round 50 source `bb3bcfe`.
- [x] Confirm A2 Round 51 real review remains pending with zero receipts, all three retained calibrations remain blocked, and shared-candidate verification remains false.
- [x] Preserve the real A2 Round 50 fact that one review is pending and zero real human dispositions exist.
- [x] Add requested, submitted, accepted, rejected and cancelled append-only events.
- [x] Derive overdue from server time without fabricating an operational event.
- [x] Require active assignment ownership for create and review actions.
- [x] Require `project:ingest` for evidence submission.
- [x] Require header-only `Idempotency-Key` and `expected_version` optimistic concurrency.
- [x] Require complete submission of every requested evidence kind and reject unrequested kinds.
- [x] Allow only A1/A2/media/provider/candidate SHA-256 evidence references.
- [x] Reject raw media, payloads, URLs, signed URLs, paths, email, identity, secrets and free text.
- [x] Validate event id/hash, previous hash, version, lifecycle, time, scope and immutable request fields.
- [x] Enforce five-level tenant scope and sanitized cross-tenant 404 behavior.
- [x] Add metadata-only audit events, Event Outbox rows and usage metering.
- [x] Persist and restore the workflow through Memory, JSON-file and SQLite stores.
- [x] Add PostgreSQL migrations 023/024 with forced-RLS contract coverage.
- [x] Add four protected API routes and keep OpenAPI runtime parity at `65/65`.
- [x] Upgrade API Reference to v13 and commercial endpoint coverage from 40 to 44.
- [x] Add evidence-request state to Dashboard, JSON, Markdown and Hosted Report exports.
- [x] Add Chinese-first create, accept, reject, cancel, denied, conflict, failure, retry and empty UI states.
- [x] Save and visually inspect desktop and 390 x 844 screenshots without document-level horizontal overflow.
- [x] Pass A3 Node `498` runnable tests with one explicit target-PostgreSQL opt-in skip and zero failures.
- [x] Pass current-main A2 `186/186` test files plus `1050` subtests without changing A2 judgement semantics.
- [x] Pass Next.js TypeScript/build with 15 pages and full Playwright `44/44`.
- [x] Pass both CL guards, both production npm audits and OpenAPI parity.
- [x] Publish feature commit `565cec7` and confirm GitHub Actions run `29322903320` passes every applicable check.
- [x] Keep `.env.local` ignored and exclude credentials, account identity, signed URLs, raw provider payloads and private media.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [ ] Import and validate a real A2 human-review receipt and complete review chain.
- [ ] Bind accepted evidence and the terminal review to one exact candidate and A2 Decision Ledger.
- [ ] Run migrations 023/024 and the complete workflow in authorized target PostgreSQL/VPC/object storage/KMS.

## 2026-07-22 - A1 commercial Compose identity follow-up

- [x] Verify fresh PostgreSQL migration 001-024 and SHA-256 replay ledger.
- [x] Verify dedicated non-superuser identity runtime login and API readiness.
- [x] Verify disposable commercial Compose API, MinIO evidence, and worker
  recovery smoke (`1 passed`).
- [ ] Do not treat local Compose evidence as hosted deployment, tenant-bound
  GitHub App proof, production upgrade/rollback proof, or A2 approval.

## A2 Round 51 Multi-repeat Stability Intake - 2026-07-14

- [x] Re-fetch authoritative main `ccf6ce5`, A1 peer `81f7e9e` and A2 peer/source `7504680`.
- [x] Re-read the enterprise strategy and preserve A1 identity and A2 evaluation/release ownership.
- [x] Record that peer-branch Round 51 evidence is not merged-main or production authority.
- [x] Build one public-safe atomic intake envelope from comparison, review collection, conservation and candidate verification.
- [x] Preserve all three complete 45-unit repeats and all three blocked retained calibration states.
- [x] Preserve 95% specificity, 20% benign false-positive rate, 30% cross-modal conflict sensitivity and 60% visual prompt-injection sensitivity across all three repeats.
- [x] Preserve one pending queue receipt, zero reviewed receipts and zero human dispositions.
- [x] Preserve shared-candidate verification false and all seven source blockers.
- [x] Add exact top-level and nested allowlists.
- [x] Recompute count, ratio, interval, hash and review conservation for integrity only.
- [x] Reject raw Provider payloads, identity, URLs, signed URLs, email, secrets, DSNs and local account paths.
- [x] Fail closed on non-empty human-review receipts until A2 publishes their exact schema.
- [x] Keep stable observation separate from quality qualification and render `blocked_stable_repeat`.
- [x] Prevent A3 from changing score, pass/fail, failure class, Decision Ledger or release authority.
- [x] Add `p3-a2-round51` to the API-backed and legacy source selectors.
- [x] Persist and restore repeat stability through Memory, JSON-file and SQLite stores.
- [x] Add protected import and read APIs with five-level scope, RBAC and sanitized denial behavior.
- [x] Add header-only idempotency, metadata-only audit, Event Outbox and usage metering.
- [x] Add repeat stability to Dashboard, JSON, Markdown and Hosted Report exports.
- [x] Keep raw payloads, identity, URLs and private media out of exported reports.
- [x] Upgrade API Reference to v14 and commercial endpoint coverage from 44 to 46.
- [x] Keep OpenAPI runtime parity at `67/67`.
- [x] Add a Chinese-first desktop/mobile Review panel without customer-facing lane badges.
- [x] Save and visually inspect desktop and 390 x 844 screenshots without horizontal overflow.
- [x] Pass A3 Node `505` runnable tests with one explicit target-PostgreSQL opt-in skip and zero failures.
- [x] Pass current-main A2 `186` tests plus `1050` subtests without changing A2 semantics.
- [x] Pass Next.js TypeScript/build with 15 pages and full Playwright `45/45`.
- [x] Pass both CL guards and both production dependency audits.
- [x] Keep `.env.local` ignored and exclude credentials, account identity, signed URLs and private media.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [x] Publish feature commit `456a193` and record successful GitHub Actions run `29329313569`.
- [ ] Import and validate a real non-empty A2 human-review receipt and terminal disposition.
- [ ] Bind the exact candidate across current A1 evidence, A2 Decision Ledger and A3 artifact.
- [ ] Run the complete workflow with hosted identity, target PostgreSQL, object storage, tenant KMS and authorized staging/VPC deployment.

## A2 Round 51 Multimodal Provider Readiness Intake - 2026-07-14

- [x] Re-check authoritative main `ccf6ce5`, A1 peer `f3071aa`, A2 peer/source `7504680` and the enterprise strategy.
- [x] Keep A1 atomic credential-link routes proposed and non-client-callable in product documentation.
- [x] Build one atomic availability and phase-latency intake envelope.
- [x] Preserve 30 attempts, 1 completion, 29 failures, 29 timeouts and 0 eligible outputs.
- [x] Preserve 0 qualified Providers and 0/4 valid structured-output profiles.
- [x] Preserve cold `74.299641s` and fastest warm `1.64026s` as diagnostic-only values.
- [x] Add exact top-level and nested allowlists.
- [x] Validate count conservation, latency order, phase residuals, hashes and model binding.
- [x] Reject release promotion, Provider truth and operational-health overclaims.
- [x] Reject secrets, tokens, cookies, URLs, email, DSNs, raw payloads, private media and local paths.
- [x] Add `blocked_provider_readiness` without changing score, pass/fail, failure class or A2 decision.
- [x] Persist and restore the projection through Memory, JSON-file and SQLite stores.
- [x] Add protected import/read APIs with five-level scope and sanitized denials.
- [x] Add header-only idempotency, audit, Event Outbox and usage metering.
- [x] Add Provider readiness to Dashboard, Review queue, JSON, Markdown and Hosted Report.
- [x] Increase commercial endpoint coverage from 46 to 48.
- [x] Add strict OpenAPI schemas and increase runtime parity from `67/67` to `69/69`.
- [x] Upgrade API Reference to v15 and document both Provider routes.
- [x] Add a Chinese-first standalone Delivery component with honest empty and blocked states.
- [x] Keep customer-facing UI free of prominent internal lane badges.
- [x] Save and visually inspect desktop and 390 x 844 screenshots without overflow.
- [x] Add implementation evidence and Growth Auditor Round 26 with 26 executable next steps.
- [x] Pass focused Provider/OpenAPI/API Reference tests `28/28`.
- [x] Pass A3 Node `513` runnable tests with one explicit target-PostgreSQL opt-in skip and zero failures.
- [x] Pass current-main A2 `186/186` without changing A2 semantics.
- [x] Pass Next.js TypeScript/build with 15 pages and full Playwright `46/46`.
- [x] Pass both CL guards and both production dependency audits.
- [x] Keep `.env.local` ignored and exclude credentials, identity, signed URLs, raw Provider payloads and private media.
- [x] Keep Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, current authority `integrity_invalid`, current A2 decision `unknown`, historical A2 `block`, and production ready false.
- [x] Publish feature commit `1809513` and confirm GitHub Actions run `29338036122` passes every applicable check.
- [ ] Obtain A1 production Provider health, routing, capacity and failover receipts.
- [ ] Obtain A2-qualified structured outputs and a real non-empty human-review disposition.
- [ ] Bind the exact current candidate across A1 evidence, A2 Decision Ledger and A3 artifact.
- [ ] Deploy with hosted identity, target PostgreSQL, object storage, tenant KMS and authorized staging/VPC receipts.

## Round 27 - A1 Round 68 / A2 Round 52 / WeChat alignment

- [x] Fetch and inspect latest A1 `566a13d` and A2 `850b39a` without merging peer branches.
- [x] Consume only A2 Round 52 public-safe aggregate facts and hashes.
- [x] Record A1 replay-retention and authorized credential-binding regression without exposing receipts or claiming a client route.
- [x] Validate exact fields, count conservation, metric ratios, quality/stability separation and authority flags.
- [x] Reject URL, DSN, token, cookie, email, local account path, Secret and raw identity receipt material.
- [x] Add `p3-a2-round52` to the Dashboard API and product source selector.
- [x] Add Web Delivery panel with controls, runtime, review, persistence and candidate gates.
- [x] Add Round 52 JSON, Markdown and Hosted Report projection.
- [x] Add OpenAPI DashboardSnapshot field and API Reference v16 metadata.
- [x] Add WeChat workbench summary without internal lane labels or local credential persistence.
- [x] Fix assignment service-clock propagation exposed by the date boundary.
- [x] Verify desktop and 390 x 844 layouts without horizontal overflow.
- [x] Pass 519 A3 Node tests, 186 current-main A2 tests, TypeScript, 15-page build and 47 Playwright tests.
- [x] Pass CL hygiene, commercial gate, diff check and production dependency audits.
- [x] Keep A2 quality blocked, candidate invalid, production receipts 0 and `production_ready=false`.

## Beginner navigation and onboarding clarity - 2026-07-22

- [x] Increase key Webapp and mobile navigation text sizes while retaining bounded layouts.
- [x] Group the sidebar into five numbered, collapsible product areas with plain-language purposes.
- [x] Show the current group, current route, current marker, and module purpose after navigation.
- [x] Add a persistent project -> run -> review -> release path and next-step cue.
- [x] Place the first-session workflow before the release verdict on Overview.
- [x] Keep the read-only demo entry visible before account creation or identity setup.
- [x] Add current-location and active-subsection behavior to both legacy Dashboard themes.
- [x] Preserve A1/A2 evidence ownership and all existing release-authority boundaries.
- [x] Pass 50 Dashboard wiring tests, 24 Webapp Playwright tests, 7 legacy Dashboard Playwright tests, TypeScript, production build, and diff hygiene.

## 2026-07-22 - A1/A3 acceptance remediation

- [x] Rebase context confirmed against remote `main` `c30a37e`.
- [x] Fix installer secret-source parity for private env files and inherited
  process variables.
- [x] Fix the dashboard zero-gradient and fail-badge visual contracts.
- [x] Require an installed and runnable WSL distribution in WSL probes.
- [x] Honor `CARGO_TARGET_DIR` in the Rust verifier contract.
- [x] Add explicit capability skips for missing Docker, Go, Node/npm,
  TypeScript, and Cargo toolchains.
- [x] A1/integration verification: `1358 passed, 68 skipped, 0 failed`.
- [x] A3 verification: `532 passed, 1 skipped, 0 failed`.
- [x] Full Playwright verification: `48 passed, 0 failed`.
- [x] Preserve the external Docker/WSL environment boundary and do not claim
  live PostgreSQL or Compose qualification.
- [x] Preserve A2 judge, Decision Ledger, and release-authority semantics.
- [x] Record remediation details in `docs/a3/acceptance_remediation_20260722.md`.

## Beginner refund demonstration - 2026-07-23

- [x] Derive one synthetic refund case from the existing A1/A2 compatibility contract.
- [x] Preserve A1 Trace and tool-call absence without inventing a successful refund result.
- [x] Preserve A2 score 42, FAIL, `missing_required_tool`, Judge evidence, and remediation semantics.
- [x] Add `refund-demo` to the fixture-backed API and Webapp source selector.
- [x] Preserve the selected source across product navigation.
- [x] Add a direct no-login demo entry from the login page.
- [x] Add plain-language Judge, rubric, failure-class, and Trace labels while retaining raw IDs.
- [x] Explain automated Judge -> human review -> delivery gate and keep unavailable write actions disabled.
- [x] Increase targeted login, evidence, Trace, Judge, and action type sizes and keep controls at least 44px high.
- [x] Add a Chinese beginner walkthrough with click order, talk track, questions, and non-production boundaries.
- [x] Add a word-for-word 10-12 minute script, 5-minute compressed script, likely Q&A, speaking boundaries, and local failure recovery steps.
- [x] Save and inspect desktop and 390 x 844 screenshots without incoherent overlap or horizontal overflow.
- [x] Pass TypeScript, Next.js build, focused A3/A1/A2 contract tests, and refund navigation Playwright tests.
- [x] Keep the demo fully redacted and avoid key, token, cookie, email, private identity, or real customer data.
- [ ] Replace synthetic refund evidence only after an authorized real sandbox run produces a redacted A1 Trace and matching A2 GradeResult.
- [ ] Enable live review actions only after hosted identity, RBAC, persistent audit storage, and authorization receipts are available.

## A1 email authentication integration - 2026-07-24

- [x] Fetch and merge A1 `780e94fc` without altering A1 identity semantics.
- [x] Replace old binding verification calls with dedicated registration and login routes.
- [x] Keep `challenge_id` and `intent_id` in component state only.
- [x] Submit the six-digit code as `proof` and never log or persist it.
- [x] Accept only same-origin HTTPS and the trusted `303 /console` handoff.
- [x] Add both email login and email registration UI states.
- [x] Keep Google/GitHub initial sign-in disabled and truthfully labelled.
- [x] Update public-safe API Reference, contract tests, and redacted capability snapshot.
- [x] Add stale-build detection, health polling, local runtime logs, and a desktop restart shortcut.
- [x] Pass 124 focused Node contracts, focused A1 Go identity contracts, TypeScript, Next.js build, focused Playwright, both CL guards, and browser overflow inspection.
- [x] Add an A1 browser-cookie identity read endpoint and use it as the A3 client identity gate.
- [x] Add an A1 browser-cookie logout endpoint that revokes PostgreSQL sessions and clears both cookies.
- [x] Verify one local HTTPS origin for A3 and `/v1/*` through Caddy.
- [x] Run PostgreSQL migrations 001-026 and verify local Mailpit OTP delivery.
- [x] Restrict Caddy to the exported Webapp directory and return `404` for repository, docs, `.env.local`, and `.local-runtime` paths.
- [x] Make browser logout idempotent when the server already reports an unauthenticated session.
- [x] Calibrate the TypeScript SaaS route-gap registry to A1 Google/GitHub initial-login browser routes without exposing OAuth codes or cookies to the generic client.
- [x] Merge A1 `6897997` and preserve applied migration immutability by restoring `026` and applying the new OAuth digest-rotation authority as `027`.
- [x] Upgrade the existing Docker PostgreSQL volume through migration `027` without deleting the persisted principal or session history.
- [x] Pass final A3 Node `536/536` with one explicit opt-in skip, Go all-package tests, TypeScript SDK `654/654`, Webapp typecheck and 15-page build.
- [x] Pass CL hygiene with zero findings, Commercial CL with zero blockers/advisories, live HTTPS route isolation checks, and browser rendering checks.
- [ ] Deploy the same-origin topology to an authorized hosted environment with server-side document-route protection.
- [ ] Configure the production identity delivery worker, SMTP/Vault secret references, and delivery receipts.
- [ ] Complete production Google/GitHub first-login coordinator and callback wiring in A1.
