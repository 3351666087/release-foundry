# A3 Official Frontend Parity Backlog - 2026-07-07

## Clean-room Boundary

This backlog is derived only from committed clean-room artifacts and the local A3 dashboard implementation. It does not use official source code, bundled implementation bodies, cookies, tokens, account data, raw signed media URLs, `.env.local`, or secrets.

Evidence used:

- `fixtures/a3/p3/releasefoundry_frontend_code_crawl_summary.redacted.json`
- `docs/a3/p3_official_frontend_code_crawl_cleanroom_2026_07_07.md`
- `docs/a3/p3_official_dashboard_gap_analysis.md`
- `apps/dashboard/index.html`

## Official Page / Module Signals

| Official signal | Clean-room evidence | A3 parity decision |
|---|---|---|
| Analysis / Datasets | Routes summarized as `?tab=analysis`, `?tab=analysis&dataset=884`, and `DatasetsPage` chunk signal. | Copy dataset -> run -> case navigation as a local review shell. |
| Results review | `CreateRequestModal` signal counts include results, expected, actual, score, timeline, audio; dashboard gap notes official Results is still visually pending for run `11926`. | Copy the review loop, but keep `visual_results_pending` explicit. |
| Runs history / run detail | Method signals include `list_runs`, `get_run`, `create_run`, `update_run_result`; A3 has `P3 Official Demo 884/11926`. | Copy read-only run listing and case detail; do not claim official visual confirmation yet. |
| Case detail | Clean-room notes map TEST DETAILS, ACTIONS, Tool Calls, media/input type. | Copy expected/actual, tool-call diff, media metadata, judge evidence, timeline. |
| Analytics | `AnalyticsPage` has pass-rate/result/dataset/agent signals. | Copy local pass-rate, score, failure clusters, coverage health. |
| Observability | `ObservabilityPage` has trace, latency, tool call, voice/audio, error signals. | Copy trace/incident replay concepts using A1 trace events and redacted metadata. |
| Usage | `UsagePage` has usage/billing/audio/voice signals; API-key probes are OAuth-gated. | Copy read-only Usage / Quota shell only. |
| Trust | `TrustPage` has trust/certificate/result signals. | Copy as local audit bundle/report/verifier concept, not public hosted trust publishing. |
| Agents | `AgentsPage` and agent tool-performance method names appear as product signals. | Copy runner/agent labels and filters only; no full registry management. |
| Folders | Folder methods appear in the clean-room method map. | Low-priority grouping only; skip for MVP unless A1 needs project grouping. |
| API Keys | `ApiKeysPage` signal exists. | Do not copy secret creation, reveal, revoke, or SDK key onboarding. |
| Team | `TeamPage` signal exists. | Do not copy invites, membership, roles, or account administration. |
| Billing / checkout | Billing method names appear under usage/billing. | Do not copy checkout, portal, subscription, or upgrade flows. |
| Login / OAuth | Lab shell includes sign-in/onboarding state and OAuth-gated usage probes. | Do not implement official auth clone; A3 stays local/read-only for MVP. |

## A3 Already Replicated

| Area | A3 implementation signal | Evidence still needed |
|---|---|---|
| Run List | `apps/dashboard/index.html` contains `Run List`, source selector `P3 Official Demo 884/11926`, and normalized case loading. | A1 run/case fixture evidence: stable `run_id`, `dataset_id`, `case_id`, status, score source ids. |
| Case Detail | Dashboard contains `Case Detail`, expected/actual panels, selected case state, judge view, and timeline view. | A1 trace/case evidence plus A2 judge result evidence for pass/fail and reason. |
| Tool Call Diff | Dashboard renders `Tool Call Diff`, expected vs actual tools, argument field diffs, and judge evidence. | A1 expected/actual tool calls plus A2 mismatch classification. |
| Trace Timeline | Dashboard maps `trace_events` or observations into timeline rows. | A1 trace events with phase/source/status and linked tool call ids. |
| Media Evidence | Dashboard has `Media Evidence`, media type badges, VM streams, and known gaps. | A1 media metadata and redacted VM/media evidence; A2 media failure taxonomy when failure is media-related. |
| Failure Clusters | Dashboard clusters failures by `primary_failure_class`. | A2 derived failure classes; A1 case ids to link examples back to traces. |
| Release Gate | Dashboard has Release Gate and release workflow sections. | A2 pass/fail/coverage thresholds plus A1 run completeness and artifact availability. |
| Report Export | Dashboard exports JSON, CSV, Markdown, and print report. | A1/A2 packaged evidence with redaction proof in exports. |
| Official ReleaseFoundry Gap Panel | Dashboard contains `Official ReleaseFoundry Gap` in UI and print report. | A3 clean-room evidence only; A1/A2 required only for case-level rows shown beside it. |
| Official Code Crawl Parity | Dashboard loads `releasefoundry_frontend_code_crawl_summary.redacted.json` and reports parity targets. | A1/A2 dependency strings from the redacted crawl summary, not official source. |

## A3 Partial Replication / Known Gaps

| Area | Current state | Evidence needed next |
|---|---|---|
| Official Results visual parity | Run `11926` exists in API-style summary evidence, but logged-in Results page confirmation is pending. | A1 run `11926` details and list-run evidence; no A2 blocker unless judging displayed failures. |
| `result.tests[].action_results[]` mapping | Clean-room doc says run `11926` proves official-style `result.tests[]`; dashboard loads that fixture. | A1 mapper fixture proving every `action_results[]` row becomes trace/tool/media evidence. |
| `result.cases[]` compatibility | Run `11925` proves A1-like `result.cases[]`. | A1 compatibility fixture so legacy and official-style run shapes normalize to the same A3 model. |
| Result visibility state | Clean-room doc proposes `not_applicable`, `empty`, `api_only`, `summary_api_visible`, `visual_confirmed`, `blocked`. | A1 page-state fixture with route hint and evidence path; A2 not required. |
| Dataset provenance | Dataset `884`, display id `#00000374`, and 5 test cases are known signals. | A1 dataset/case provenance fixture with display id and frontend case key. |
| Usage / Quota | UI modules observed, API-key access OAuth-gated. | A1 usage/quota calibration fixture with only channel labels and gated status; A2 not required. |
| Observability Replay | Dashboard has incident/observability replay matrix; official Observability signal is name/count-level. | A1 trace/latency/error/tool-error events; A2 remediation labels for reviewer action. |
| Analytics Trend | A3 has local summary analytics but not official account-level charts. | A1 historical run set; A2 score/pass/failure class trend evidence. |
| Trust / Audit | A3 reports local audit bundles; official trust certificate is only inspiration. | A1/A2 evidence packaged with verifier metadata; no official public certificate clone. |
| Media Rendering | A3 shows metadata but does not render live signed URLs. | A1 redacted media metadata and redaction proof; A2 failure taxonomy for media cases. |

## Not Replicated: Admin / Cloud / Billing / Key / Team / Login Logic

| Official area | Backlog decision | A1 or A2 evidence rule |
|---|---|---|
| API key creation/reveal/revoke | Keep out of scope. Never store, print, or simulate real secret workflows beyond safety copy. | No A1/A2 business evidence required; only A3 redaction checks should prove exports contain no keys. |
| Team invites/member roles | Keep out of scope. No invite, role, organization, or account admin UI for MVP. | No A1/A2 business evidence required; if a shell row is shown, it must be static A3 boundary evidence. |
| Billing checkout/portal/upgrade | Keep out of scope. Usage can be read-only; billing mutation stays blocked. | No A1/A2 business evidence required; A1 can provide gated usage status only. |
| Login/OAuth/session management | Keep out of scope. A3 should not clone official auth or save session state. | No A1/A2 business evidence required; A3 safety evidence must prove no cookies/tokens are exported. |
| Hosted cloud object mutation | Do not create/delete/publish/invite/mutate official cloud objects from A3 MVP. | A1/A2 fixtures should be read-only snapshots; mutations require separate approval outside this backlog. |
| Public Trust hosting | Do not publish official-like public certificates. Keep local report/export/verifier only. | A1/A2 evidence can be bundled locally; no hosted trust artifact required. |

## Next Backlog Items

| # | Item | Type | Acceptance target | Needs A1 or A2 evidence |
|---:|---|---|---|---|
| 1 | Add `official_frontend_page_state` fixture with `dataset_visible`, `results_empty`, `frontend_style_run_visible_api`, and `visual_results_pending`. | Fixture | JSON fixture validates route hints, visibility state, decision, blocked reason. | A1 page/run visibility evidence; A2 not required. |
| 2 | Add `result_visibility` enum to mapper/report schema. | Schema | Reports distinguish `api_only`, `summary_api_visible`, `visual_confirmed`, and `blocked`. | A1 run/list/page-state evidence; A2 not required. |
| 3 | Normalize run `11926` `result.tests[].action_results[]`. | Mapper | Every test/action maps to A3 case, tool diff, trace event, media metadata. | A1 action result evidence; A2 score/failure evidence where present. |
| 4 | Keep run `11925` `result.cases[]` regression coverage. | Mapper test | Legacy shape and official-style shape produce comparable A3 case records. | A1 run/case evidence; A2 optional for failure class normalization. |
| 5 | Show source provenance labels beside each dashboard evidence block. | UI | UI distinguishes official UI observation, redacted API evidence, and local A1/A2 fixtures. | A1 source ids and evidence paths; A2 judge source ids. |
| 6 | Add visual pending badge for official Results page. | UI | Dashboard says run `11926` is summary-API visible, visual Results confirmation pending. | A1 list-run/page-state evidence; A2 not required. |
| 7 | Strengthen dataset provenance card. | UI | Show dataset id, display id, request provenance, case count, route hint. | A1 dataset/case/request evidence; A2 not required. |
| 8 | Polish case detail labels to match official concepts without copying style/code. | UI | TEST DETAILS/ACTIONS-equivalent sections are clear in A3 language. | A1 case/action/tool/media evidence; A2 judge reason/score. |
| 9 | Add trace latency/error lanes to Observability Replay. | UI/report | Replay matrix can separate trace completeness, latency/error, tool error, media evidence. | A1 trace timestamps/errors/tool events; A2 remediation labels. |
| 10 | Add pass-rate/run-volume local analytics trend. | UI/report | Analytics card summarizes pass rate, run volume, failure class trend across fixtures. | A1 historical runs; A2 pass/fail/score/failure class. |
| 11 | Add usage/quota known-gap panel fixture contract. | Fixture/test | Usage channels are labels only; OAuth-gated status is explicit. | A1 usage/quota calibration evidence; A2 not required. |
| 12 | Add redaction regression for JSON/Markdown/CSV exports. | Test | Exports fail if they contain key/token/cookie/email/raw signed URL patterns. | A1/A2 exported fixtures; A3 redaction scanner evidence. |
| 13 | Add report section for official frontend page-state parity. | Report | Markdown and JSON reports include page/module parity and blocked states. | A1 page-state evidence; A2 only for case/failure rows in the same report. |
| 14 | Add Trust-inspired local verifier summary. | Report | Report lists artifact manifest, evidence hash/status, and verifier outcome locally. | A1/A2 packaged evidence in audit bundle. |
| 15 | Add admin/cloud non-goal section to report exports. | Report | Exports explicitly say API keys, team, billing, OAuth, hosted mutations are not implemented. | No A1/A2 business evidence; A3 boundary evidence only. |
| 16 | Add dashboard wiring test for `api_only` vs `summary_api_visible`. | Test | UI text changes based on result visibility state. | A1 page-state/run-list fixture; A2 not required. |
| 17 | Add dashboard wiring test for `visual_results_pending`. | Test | Pending state remains visible until logged-in browser evidence updates it. | A1 page-state evidence; A2 not required. |
| 18 | Add mapper test linking A2 judge evidence to tool-call diff rows. | Test | Tool diff rows show judge mode, score, failure class, trace/tool ids. | A1 tool/trace ids plus A2 judge evidence. |
| 19 | Add media metadata fixture with redacted channels only. | Fixture | Image/audio/file/video/VM metadata renders without live signed URLs. | A1 media metadata; A2 media failure class when case fails. |
| 20 | Add empty workspace / empty results state. | UI/test | A3 can render no datasets/runs/cases without confusing it with failed load. | A1 empty state fixture; A2 not required. |
| 21 | Add request-generation provenance lane. | UI/report | Request id/status/source prompt metadata appears when fixtures provide it. | A1 request lifecycle evidence; A2 not required. |
| 22 | Add runner/agent filter parity. | UI | Agent/runner labels filter cases without implementing official agent registry admin. | A1 runner/agent metadata; A2 aggregate score/failure class by runner. |
| 23 | Add reviewer workflow action checklist. | UI/report | Failed cases show missing evidence, reviewer owner/state, next action. | A1 trace/evidence completeness; A2 remediation and severity. |
| 24 | Add release gate CLI/report parity assertion. | Test/report | Release gate consumes same normalized A1/A2 evidence as dashboard/report. | A1 run completeness and artifacts; A2 coverage/score/failure thresholds. |
| 25 | Add logged-in browser follow-up protocol, not credentials. | Ops doc | Procedure says what page/state to observe and what redacted fixture to update, without saving cookies/tokens. | A1 visual observation fixture; A2 not required. |
| 26 | Add fixture-contract test for no official source/code snippets. | Test | Redacted crawl fixtures contain names/counts/decisions only. | No A1/A2 business evidence; A3 clean-room evidence only. |

## Evidence Ownership Notes

- A1 owns raw run, dataset, case, trace, tool-call, action-result, request, media metadata, usage calibration, and page-state evidence.
- A2 owns judge outputs, pass/fail, score, failure taxonomy, severity, remediation, coverage, and release threshold evidence.
- A3 owns local dashboard/report rendering, clean-room parity decisions, safety boundaries, redaction checks, and backlog prioritization.

## Failure Points To Keep Visible

- Official Results-page visual parity is still pending for run `11926`; current evidence is API/list-run shaped, not logged-in UI confirmation.
- Native official `failure_class` is unconfirmed; A3 should keep using A2-derived `primary_failure_class`.
- Live signed media rendering remains blocked by safety/redaction concerns.
- Usage/quota is frontend-confirmed but API-key probes are OAuth-gated.
- Admin/cloud workflows are intentionally excluded even though their page/module names exist in the clean-room summary.

## Next Strike Zone

1. Implement the page-state fixture and result visibility enum first.
2. Add mapper tests for both run shapes: `11925` `result.cases[]` and `11926` `result.tests[].action_results[]`.
3. Wire page-state parity into dashboard JSON/Markdown/print reports.
4. Add export redaction regression before any new official-demo fixture is allowed.
5. After a fresh logged-in browser pass, update `visual_results_pending` to `visual_confirmed` or `blocked` with a redacted observation fixture.
