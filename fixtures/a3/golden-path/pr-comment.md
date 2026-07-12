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
