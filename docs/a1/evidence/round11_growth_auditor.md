# A1 Round11 Bus / Growth-Auditor Report

Date: 2026-07-07
Branch: `codex/a1-local-sdk-runner`
Repo: `C:/Users/33516/Documents/Ashr`
Latest observed commit: `0970328 A1: bind quota gates to fresh request evidence`

## Baseline Branch And Peer Impact

- Baseline status: `git status -sb --untracked-files=all` reported a clean worktree on `codex/a1-local-sdk-runner...origin/codex/a1-local-sdk-runner`.
- Target file state: `docs/a1/evidence/round11_growth_auditor.md` did not exist at baseline.
- Scope honored for this pass: only this report file was created. No code, schemas, private refs, tests, or shared docs were edited.
- Safety posture: no private key files were read, no ignored private evidence payloads were opened, no environment secrets were inspected, and no paid or mutating API calls were made.
- Peer impact: clean baseline means there were no visible uncommitted peer edits to preserve at start. Recent public docs show Round10 integrated multiple peer/subagent changes across Python probe, Python calibrator, TS probe, TS calibrator, schema, and tests; Round11 work should assume those surfaces are active and coordinate before broad refactors.
- Current A1 center of gravity: Round10 moved A1 from basic quota-gate enforcement to request-bound quota-gate validation with TTL and real read-only calibration evidence. The next risk is less "is there a gate?" and more "is the gate consistently generated, validated, published safely, and consumed by other lanes?"

## Target Drift Risks

- TS execution-side gate validation exists, but TS still lacks standalone `plan-batch` and `validate-gate` generator parity. This can drift from Python as the schema evolves.
- The public evidence index stayed at the prior 326-record snapshot after Round10, while new real read-only calibration manifests remained private. Public status can look stale even when private evidence improved.
- Private-output safety is convention-based for custom `--output`; a caller can still point real/gate records outside `docs/evidence/private_refs` unless a guard is added.
- Request-bound gates reduce mutation risk, but future planner changes could silently alter fingerprint fields unless fixture snapshots lock the canonical inputs.
- TTL defaults are now documented as `86400`, but stale-gate behavior must remain consistent across Python probe, Python calibrator, TS probe, and TS calibrator.
- Dashboard Usage values are manually observed read-only evidence, not an importable quota source. Manual transcription can drift from current product state.
- The hosted API read-only shape is current as of Round10, but there is no scheduled drift checker for official docs or API response keys.
- Quota gate schema is public, but schema validation is not yet clearly enforced as a CI contract for all committed gate examples.
- No mutating paid API success path has been proven after the new request-bound gate; A1 still knows how to block safely better than it knows how to complete a paid small batch safely.
- Override audit exists in emitted records, but there is no public override event manifest with redacted reason hashes and operator-safe metadata.

## Owned-Dir And Contract Risks

- A1-owned code spans Python runner/probe, Python SDK/calibrator, TS SDK/probe/calibrator, local cloud/queue, evidence builders, and docs under `docs/a1`. Changes in one surface can easily leave another surface one round behind.
- A2/A3 consume A1 evidence and runner shapes. Any change to run fixtures, trace envelopes, evidence index fields, or quota-gate status summaries should preserve backward compatibility or publish a clear version bump.
- `field_map_version`, quota-gate schema versions, and target-binding schema versions are now contract identifiers. Reusing them for incompatible behavior would make historical evidence ambiguous.
- Public docs must not contain raw private payloads. Round10 correctly kept real API manifests private, but future public index refreshes must summarize only redacted keys/counts.
- `docs/evidence/private_refs` paths are referenced by public docs. The path names are useful provenance, but the contents must remain ignored/private.
- The schema allows additional properties for forward compatibility. That is useful, but consumers need tests for the required minimum fields so optional drift does not become accidental dependency.
- Calibrator modality binding is a cross-language contract. Python and TS should agree on modality order, fingerprint scope, and how text-only versus media requests are represented.
- Local cloud/queue quota fields use similar words (`quota`, `limits`, `used`, `remaining`, `batch_size`) but are not the same as hosted Ashr quota gates. Reports should avoid blending local quota simulation with hosted paid-call authorization.
- A3 dashboards may want a simple readiness badge, but A1 should expose a public-safe gate summary rather than making A3 inspect private records.
- A2 judges and scenario coverage should consume stable run/result/trace artifacts; A1 should avoid changing those shapes while chasing API calibration unless the shared contract is updated.

## Evidence Gaps

- No public round11 validation results exist yet for the current branch beyond the clean baseline checks in this pass.
- Round10 private real read-only Python and TS calibration manifests were not merged into the public evidence index.
- There is still no successful real mutating `create_request` or `create_run` evidence under the request-bound quota gate.
- There is no automated parser for Usage dashboard quota counters or reset windows.
- There is no reusable public report that summarizes gate validation outcomes across Python/TS surfaces without exposing private payload details.
- There is no CI or preflight linter that rejects custom real-output paths outside private evidence directories.
- There is no shared fixture suite that every Python/TS gate consumer imports for stale, wrong-target, wrong-request, no-evidence, stop, wait, and override cases.
- There is no documented disaster path for an accidental override: who reviews, what evidence is public, and how the next gate is reset.
- Official docs drift is manually checked. There is no stable watcher for Python SDK, TypeScript SDK, VM integration, Usage dashboard labels, or API reference field names.
- Evidence still leans heavily on private files and worklog summaries; A1 needs a compact, public-safe "current commercial readiness" artifact.

## Next Growth Points

1. Add TS `plan-batch` generation parity with Python, including request fingerprints and target binding.
2. Add TS standalone `validate-gate` CLI parity with Python output schema.
3. Create a shared Python/TS quota-gate fixture directory for stale, wrong target, wrong request, stop, wait, no-evidence go, and audited override cases.
4. Enforce private output directories for real API records unless an explicit unsafe escape flag is present.
5. Add a public-safe quota-gate validation summary artifact for A2/A3 consumption.
6. Merge Round10 read-only calibration summaries into the public evidence index without exposing private payloads.
7. Add an override audit manifest that records redacted reason hashes, gate ids, target operation, TTL, and validation issue codes.
8. Add Usage dashboard import tooling for Images, Audio, Files, period start, and upgrade labels without recording secrets or API keys.
9. Add quota reset detector fixtures from read-only response headers and dashboard reset hints.
10. Add request fingerprint schema docs with canonical field order and examples for text-only and media requests.
11. Add CI validation for `docs/a1/schemas/api_probe_quota_gate.schema.json` against committed public examples.
12. Add a stale-gate committed-doc linter so public examples cannot imply that old gates are executable.
13. Add a real read-only calibration schedule and freshness badge for Python and TS.
14. Add official docs drift checker for Python SDK overview, TS SDK API reference, VM integration, and Observability terms.
15. Add field-map freshness checks that warn when private evidence is newer than public index summaries.
16. Split public response field-map `unknown` buckets into typed categories for API error, quota error, pagination, and user/session envelopes.
17. Add a safe small-batch mutating text path that only runs after fresh request-bound go evidence and explicit human approval.
18. Add post-mutation polling plan for a successful hosted request, still gated by quota and private-output controls.
19. Add local replay ingestion for any future hosted successful request, preserving A3-compatible traces.
20. Add A1-to-A2/A3 handoff notes for quota-gate readiness states and what downstream lanes may safely trust.
21. Add enterprise audit export format for gate decision, target binding, TTL age, override metadata, and validation issue codes.
22. Add a public "no paid mutation executed" marker when rounds intentionally stop at read-only evidence.
23. Add contract tests ensuring Python and TS calibrators produce equivalent gate summaries for the same fixture.
24. Add contract tests ensuring Python and TS probes reject the same bad gate fixtures before key lookup.
25. Add release checklist requiring clean status, no private refs opened, no mutating API calls, public linter pass, and current branch/commit provenance.
26. Add docs for how to rotate or expire private gate records without deleting historical public provenance.
27. Add a dashboard-ready A1 commercial readiness badge with states: read-only current, gate current, mutation blocked, mutation approved, mutation completed.
28. Add a cross-lane "owned paths" map so future Bus tasks can see A1/A2/A3 boundaries before editing.
29. Add schema version migration guidance for `ashr.clone.api_probe_batch_plan.v1`, `ashr.clone.api_probe_gate_validation.v1`, and `ashr.clone.api_probe_target_binding.v1`.
30. Add a final Growth-Auditor checklist that prioritizes evidence safety regressions over new calibration breadth.

## Round11 Recommendation

The strongest next move is to turn Round10's validator work into durable contracts: TS generator parity, shared bad-gate fixtures, private-output enforcement, and a public-safe gate validation summary. Those reduce drift across A1 surfaces and give A2/A3 a stable signal without increasing paid-call or secret-handling risk.

## Final Post-Implementation Audit

Implementation summary provided for this audit:
- TS probe standalone `plan-batch` and `validate-gate` parity was implemented.
- Tests were added for the new TS probe gate planner/validator path.
- Real read-only TS API probes were run; no paid or mutating API calls are reported for this audit.
- Public evidence index was refreshed to 333 records with lint issues 0.
- Validation reported: `npm test --prefix packages/ts/ashr-clone` passed with 172 tests; `python -B -m pytest tests/a1` passed with 189 tests; readiness smoke passed; `git diff --check` exited 0 with CRLF warnings only; secret scan matched only historical pattern docs and synthetic `tp_syntheticsecret`.

### P0 Findings

- None found from the reported implementation and validation results.
- No evidence of paid or mutating API execution was reported.
- No evidence of operational secret exposure was reported; the only scan hits were historical docs patterns and synthetic test strings.
- The public evidence linter result is clean at 333 records and lint issues 0.

### P1 Findings

- None blocking commit.
- Prior Round11 target drift around TS standalone `plan-batch` / `validate-gate` parity is reported as implemented.
- Prior public-evidence freshness risk is materially reduced by the reported evidence index refresh to 333 records with lint issues 0.
- Cross-suite validation is strong for this scope: TS package tests, full A1 Python tests, readiness smoke, diff check, and secret scan all passed or had expected benign warnings.

### P2 Findings

- Confirm in the commit message or PR body that real API activity was read-only only, so reviewers do not infer mutating coverage from the refreshed evidence index.
- Keep the CRLF warning noted as benign; no whitespace errors were reported by `git diff --check`.
- The secret scan result should remain attached to the final evidence trail because the synthetic `tp_syntheticsecret` hit is expected but easy to misread later.
- TS parity is now reported complete for standalone planner/validator behavior, but future rounds should still watch Python/TS schema drift as new gate fields are added.

### Commit Readiness

Commit can proceed for the reported Round11 implementation, assuming the staged diff is limited to the intended TS probe parity, tests, public evidence refresh, and this audit/evidence documentation. There are no P0 or P1 blockers in this post-implementation audit.
