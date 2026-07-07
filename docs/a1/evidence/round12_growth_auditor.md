# A1 Round12 Growth / Bus-Auditor Report

Date: 2026-07-07
Repo: `C:/Users/33516/Documents/Ashr`
Branch: `codex/a1-local-sdk-runner`
Baseline HEAD: `22007d6`

## Baseline

- Local branch check: `codex/a1-local-sdk-runner`.
- Local HEAD check: `22007d6`, matching the requested Round12 baseline.
- Worktree baseline: clean before this report was created.
- Target file state: `docs/a1/evidence/round12_growth_auditor.md` did not exist before this pass.
- Scope: this pass creates only this public audit file.
- Safety: no secrets, private key files, ignored private evidence files, raw private evidence payloads, environment variables, or API endpoints were read. No API calls were made.

## Peer Impact

- Local refs show branch divergence from `origin/main`: `origin/main` is 1 commit ahead and this A1 branch is 6 commits ahead.
- The ahead commit on `origin/main` is `9ddaeb2 Rewrite project README`, touching `README.md`.
- Peer impact risk is documentation-facing rather than runtime-facing: the README rewrite may change public project framing, setup steps, safety language, or task ownership wording that A1 evidence docs should mirror before merge.
- A1 branch divergence means future merge/rebase work should expect a README conflict or semantic mismatch even if the file-level conflict is simple.
- This report does not inspect or rewrite README contents. The next implementation pass should review README changes deliberately and avoid overwriting peer wording.

## Target Drift Risks

- Round11 reportedly completed TS probe standalone `plan-batch` and `validate-gate` parity; Round12 should prevent that parity from drifting as Python planner fields evolve.
- Public evidence index refreshes can lag private real read-only probes. If public summaries are not refreshed after each calibration round, downstream A2/A3 readers may trust stale counts.
- Private-output-dir enforcement is still the major safety gap. A real read-only or gate-validation run with a custom output path can accidentally write private payload summaries outside ignored storage unless blocked.
- README rewrite on `origin/main` can change user-facing command names or safety expectations, while A1 docs continue to cite older workflows.
- Quota-gate schema, validation schema, and target-binding schema are now contracts. Optional field growth can become breaking drift if Python and TS do not share fixtures.
- TS standalone planner parity may still differ in edge cases: BOM handling, request fingerprint canonicalization, schema fingerprint nullability, modality order, and TTL timestamp parsing.
- Evidence linter count of 0 is useful, but it does not prove private-output safety unless output path policy is part of the linter or CLI guard.
- Real read-only probes are safe relative to mutating calls, but they still use real credentials and must stay in private evidence paths.
- Secret scans can match historical or synthetic values. Without a stable allowlist/explanation pattern, future reviewers may waste time or miss a real leak.
- No paid mutating success path should be inferred from read-only evidence or gate validation evidence.

## Owned-Dir And Contract Risks

- A1 owns or heavily influences `services/runner/api_probe.py`, `packages/sdk/ashr_clone/calibrate.py`, `packages/ts/ashr-clone/src/probe.ts`, TS tests, Python A1 tests, evidence builders, and `docs/a1` evidence.
- A1 public evidence is consumed by A2/A3. Public schemas and evidence index shape changes need compatibility review before merge.
- `docs/evidence/private_refs` is a convention and an evidence boundary. A1 should enforce it in runtime paths, not rely only on operator discipline.
- The README rewrite on `origin/main` may redefine cross-lane expectations. A1 docs should not hard-code stale setup or safety language after merging main.
- Public evidence index summaries must avoid raw response payloads, request bodies, API keys, authorization header values, emails, and private dashboard counters.
- Gate validator output should be public-safe by design: issue codes, timestamps, target operation, hashes, and counts are acceptable; raw request/evidence payloads are not.
- Request fingerprints are safe only if canonicalization excludes raw payload emission and remains deterministic across Python and TS.
- A2/A3 readiness badges should depend on summarized gate states, not private evidence file contents.
- Local cloud quota simulation and hosted API quota gates share terms but not authority. Contracts should keep local quota tests separate from paid API authorization.
- Schema version bumps should happen when behavior changes incompatibly; otherwise historical gate validation artifacts become ambiguous.

## Evidence Gaps

- No Round12 private-output-dir enforcement implementation is recorded yet.
- No Round12 post-merge README alignment review is recorded yet.
- No public checklist yet states which commands are allowed to write outside private refs and which must be blocked.
- No shared bad-gate fixture matrix is documented as the source for both Python and TS planner/validator tests.
- No current public artifact summarizes Round11/12 gate validation readiness in a compact downstream-readable form.
- No automated proof is recorded that custom `--output` paths are rejected for real API records and gate validation records.
- No explicit reviewed exception process exists for intentionally writing redacted public summaries from private records.
- No evidence here proves mutating API success; A1 remains in safe read-only/gated posture.

## Pre-Audit Criteria For Private-Output-Dir Enforcement

Before implementation is considered ready for post-audit, the following criteria should be met:

1. Define the protected output classes: real API probe records, real calibration manifests, per-step real calibration records, gate validation records that reference private gate files, and any generated quota/reset evidence.
2. Define the allowed private root as `docs/evidence/private_refs` by default, resolved to an absolute normalized path.
3. Reject custom output paths outside the private root for protected output classes before API key lookup, client construction, or file write.
4. Preserve dry-run public-safe output behavior where no private payload or real credential context is involved.
5. Add an explicit escape hatch only if necessary, with a long audit reason and clear warning text. Default should be deny.
6. Ensure path traversal attempts such as `../`, absolute paths outside the repo, symlinks, and mixed slash styles cannot bypass the guard.
7. Ensure Windows drive-letter and case-insensitive path behavior is tested.
8. Ensure `--output -` behavior is reviewed separately; printing real private records to stdout should be denied unless explicitly designed safe.
9. Keep error messages public-safe: mention the policy and path class, not secrets or raw payload content.
10. Add Python probe tests proving rejection happens before API key lookup.
11. Add Python calibrator tests proving rejection happens before API key lookup.
12. Add TS probe tests proving rejection happens before API key lookup.
13. Add TS calibrator tests if the TS calibrator accepts real output paths.
14. Add tests for allowed paths under `docs/evidence/private_refs`.
15. Add tests for rejected paths under `docs/a1`, repo root, temp directories, and parent traversal.
16. Add docs/evidence note explaining the policy and why private refs are required.
17. Run `python -B -m pytest tests/a1 -q -p no:cacheprovider`.
18. Run `npm test --prefix packages/ts/ashr-clone`.
19. Run readiness smoke without opening raw private evidence.
20. Run `git diff --check` and a public touched-file secret scan.

## Growth Points

1. Implement private-output-dir enforcement for Python API probe real records.
2. Implement private-output-dir enforcement for Python calibrator real manifests and step records.
3. Implement private-output-dir enforcement for TS probe real records and gate validation outputs.
4. Audit TS calibrator output behavior and add the same enforcement where applicable.
5. Add shared path-policy helper tests for Windows path normalization.
6. Add `--output -` denial for protected real/private output classes unless a safe summary mode is used.
7. Add a public-safe summary mode that prints only status, issue codes, and output path.
8. Add a long-form override reason for any future unsafe output escape hatch.
9. Add a public evidence note documenting private refs as the only allowed real-output target.
10. Add README merge review after `origin/main` rewrite is integrated.
11. Align A1 command docs with the rewritten README without overwriting peer wording.
12. Add shared Python/TS quota-gate fixtures for standalone planner and validator parity.
13. Add CI schema validation for committed quota-gate examples.
14. Add evidence-index freshness check after real read-only probes.
15. Add public-safe gate validation rollup for A2/A3 dashboards.
16. Add round-level marker that no paid/mutating API calls were executed.
17. Add Usage dashboard parser for public-safe quota labels without raw counters unless approved.
18. Add official docs drift checker for Python SDK, TS SDK, VM Integration, and Observability.
19. Add request fingerprint canonicalization docs and cross-language snapshot tests.
20. Add target-binding schema migration notes for future fields.
21. Add stale-gate linter for docs/examples.
22. Add response field-map freshness badge and stale warning.
23. Split public evidence field-map unknown categories into actionable groups.
24. Add public secret-scan allowlist notes for synthetic `tp_` test values.
25. Add private evidence rotation guidance that preserves public provenance.
26. Add A1/A2/A3 owned-path map to reduce cross-lane accidental edits.
27. Add release checklist requiring branch divergence review against `origin/main`.
28. Add post-merge README smoke check for documented commands.
29. Add explicit no-mutating-call preflight checklist for audit-only rounds.
30. Add post-implementation auditor template with P0/P1/P2 findings and commit readiness.

## Round12 Recommendation

Treat private-output-dir enforcement as the next P1 implementation target. The TS planner/validator parity work improved gate correctness; output-path enforcement is the matching safety layer that prevents real read-only or gate-validation evidence from escaping private storage. Merge planning should also account for `origin/main` rewriting `README.md` while this A1 branch remains 6 commits ahead.
