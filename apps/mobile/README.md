# A3 Mobile Client Surface

This directory is the React Native / Expo client-surface contract for A3. It is intentionally small: the first mobile use case is release approval and incident alert review, not a full dashboard clone.

## Scope

- Show release gate status from A3 Release Evidence.
- Show incident replay alerts from A3 Incident Replay.
- Show reviewer workflow tasks and hosted report links.
- Keep all real cloud mutation, billing mutation, team invite, API key reveal, and Trust publish operations disabled until hosted auth/RBAC exists.

## A1 / A2 / A3 Contract

- A1 provides RunResult, Trace, Observation, ToolCall, and agent response evidence.
- A2 provides GradeResult, score, pass/fail, release gate, failure taxonomy, and commercial readiness evidence.
- A3 provides Release Evidence, hosted report, reviewer workflow, usage/audit summaries, and redacted artifact references.

## Safety

The mobile surface must not store API keys, raw share tokens, cookies, Authorization headers, signed URLs, emails, or account identifiers. It only renders redacted IDs, hashes, status labels, and deep links that are issued by A3 after redaction.
