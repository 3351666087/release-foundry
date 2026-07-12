# Ashr++ Gate CLI Report

- Command shape: ashr gate --json
- Source: a3-golden-path
- Run: a3-golden-20260712-001
- Decision: Block release
- Risk score: 87
- Check conclusion: failure
- Blocks merge: yes
- A2 authority: blocked
- A2 upstream decision: block
- A2 release ready: no
- Waiver: Blocked releases require an explicit executive exception and a one-day expiry.

## Audit Manifest

- runs: 765a566732207e105d1856d8aa01dbbdb93f4fae9e85131e1b6fb1c77242d2fd (fixtures/a3/golden-path/a3_new_run_result.redacted.json)
- grades: 8cbcb2bb8a6d16c906d374868738cc8df30bfa22b405e209e66c8229c940dc54 (fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json)
- coverage: 3e5f8c572056c38c38d93361c64ef6e76850a1e8a5716947c48be6b0cc19d14f (fixtures/a2/results/a2_g3_coverage_report.json)
- thresholds: fb4360ed42e60a4d8123ccb432bf968cb200f7fe22554e158b1b8a5ac3426729 (fixtures/a3/release_gate_thresholds.json)

## Waiver Review

- Status: missing_required_waiver
- Accepted: no
- Automatic unblock: no
- Reason: Release requires waiver evidence, but no waiver file was provided.

## Approval Review

- Status: missing_required_approval
- Accepted: no
- Automatic unblock: no
- Reason: Release requires approval evidence, but no approval file was provided.

## PR Comment

## Ashr++ Release Gate

Decision: **Block release**
Risk score: **87**
Release: `0.2.0-rc.1`
Environment: `staging`
Owner: Release owner

| Signal | Value |
|---|---|
| Run | `a3-golden-20260712-001` |
| Pass rate | 33.3% |
| Average score | 80.7 |
| Trace completeness | 100% |
| Failed checks | pass_rate, required_tool_coverage |
| PR gate next action | Block merge: resolve A3 failed check(s) pass_rate, required_tool_coverage before sign-off. |
| Sign-off risk | blocked |

### Required Reviewers

- Release owner
- A3 triage owner
- A1 runner/tooling owner

### Top Risk Cases

- `a3-gp-required-web-tool`: missing_required_tool / major / 71 - Required tool missing: web.search
- `a3-gp-media-pipeline`: missing_required_tool / major / 71 - Required tool missing: media.fetch; Required tool missing: image.view; Required tool missing: media.classify; Tool order violated: media.fetch before image.view; Tool order violated: image.view before media.classify

### Reviewer Gate

- Next action: Block merge: resolve A3 failed check(s) pass_rate, required_tool_coverage before sign-off.
- Sign-off risk: blocked (87)
- A2 blockers: none
- A1 trace/tool-call evidence: trace 2, tool diffs 0

### Reviewer Lanes

- A1 trace/tool-call evidence: ready / A1 API/runtime owner - Replay 2 A1 trace-ready case(s) and inspect 0 tool-call diff packet(s).
- A3 PR gate action: blocked / A3 dashboard/report owner - Publish the PR gate next action with the report, then require reviewer disposition before merge.
