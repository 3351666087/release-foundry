# A3 Growth Auditor Round 25: Multi-repeat Stability Intake

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: A2 Round 51 repeat stability, review conservation, candidate binding, persistence, API, reports and Review UI

## Verdict

Round 25 converts a real A2 multi-repeat calibration artifact into a customer-readable product workflow. An
operator can now distinguish reproducibility from quality: all three 45-unit repeats are complete and stable,
but all three are blocked, human review is still pending, and shared-candidate verification is false.

This is useful evaluation observability, not release authority. A stable failure is still a failure. A3 does not
recompute A2 metrics, create a human disposition, promote a candidate, or change the authoritative release state.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Atomic Round 51 intake | implemented locally | comparison, review and candidate facts cannot be partially mixed |
| Exact schema allowlists | implemented | unknown or unsafe fields fail closed |
| Count/ratio/hash conservation | implemented | malformed aggregate evidence is rejected |
| Stable-vs-qualified split | implemented | repeatability cannot be presented as PASS |
| Human-review conservation | implemented for empty receipts | pending queue facts remain visible and honest |
| Non-empty human receipt | intentionally blocked | exact authoritative receipt schema is still missing |
| Five-level tenant scope | local contract tested | cross-tenant access fails closed |
| Memory/JSON/SQLite durability | test-proven | supported local restart paths preserve the projection |
| Audit/outbox/usage/idempotency | implemented locally | imports enter enterprise operations pipelines |
| JSON/Markdown/Hosted Report | implemented | aggregate evidence is portable without raw payload leakage |
| Chinese-first responsive UI | implemented | operators can understand the blocker on desktop and mobile |
| A2 release decision | unchanged | A3 remains a read-only consumer of A2 authority |
| Production identity/storage/deployment | missing | local evidence is not production acceptance |

## 25 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Publish the exact non-empty A2 human-review receipt schema | blocker | A2 | closed schema, signer, predecessor and hash rules |
| 2 | Import one public-safe real human-review receipt | blocker | A2/A3 | positive, duplicate, reorder, fork and tamper tests |
| 3 | Complete the pending Round 51 review collection | blocker | A2 | independently verified disposition and conservation receipt |
| 4 | Bind all three repeats to one exact candidate ID | blocker | A1/A2 | matching Git SHA, run, artifact and calibration hashes |
| 5 | Bind the final review to the same-candidate Decision Ledger | blocker | A2/A3 | verified ledger record and terminal review hash |
| 6 | Rebuild the Trusted Spine after candidate convergence | blocker | A1/A2/A3 | fresh spine with valid end-to-end integrity |
| 7 | Raise specificity to the authoritative A2 threshold | high | A2 | retained calibration marked qualified by A2 |
| 8 | Reduce benign-text false positives below policy threshold | high | A2 | repeated confidence interval and policy comparison |
| 9 | Improve cross-modal conflict sensitivity above 30% | high | A2 | new retained repeats with complete units |
| 10 | Improve visual prompt-injection sensitivity above 60% | high | A2 | adversarial regression pack and retained repeats |
| 11 | Add latency and availability evidence to repeat projection | high | A1/A2/A3 | bounded schema and fail-closed timeout states |
| 12 | Bind Provider identity without exporting raw credentials | high | A1/A2 | workload/provider attestation hash |
| 13 | Link A1 trace and tool-call custody to each calibration unit | high | A1/A3 | immutable artifact readback and retention receipt |
| 14 | Add authorized media preview through a controlled proxy | high | A1/A3 | tenant auth, expiry, checksum and access audit |
| 15 | Add dual-review policy for high-risk media cases | high | A2/A3 | two distinct qualified reviewer receipts |
| 16 | Add SLA aging and escalation for pending review | medium | A1/A3 | deduplicated worker, retry, dead-letter and audit evidence |
| 17 | Add WeCom, DingTalk and Feishu review notifications | medium | A1/A3 | signed delivery and retry receipts |
| 18 | Qualify the projection on target PostgreSQL with forced RLS | blocker | A1/A3 | migration, cross-scope denial, restart and rollback receipts |
| 19 | Move retained evidence to controlled object storage | blocker | A1/A3 | checksum, tenant scope, retention, deletion and recovery |
| 20 | Bind hosted reviewer identity to enterprise SSO | blocker | A1/A3 | session, MFA, CSRF, qualification and conflict checks |
| 21 | Make unresolved required review fail a tenant GitHub App Check | blocker | A1/A2/A3 | installation identity and real merge denial |
| 22 | Add cohort trends without exposing case or reviewer identity | medium | A3 | privacy-safe metric definitions and 10k-row load test |
| 23 | Export signed repeat evidence in the next Audit Bundle | high | A3 | candidate-bound manifest and tenant KMS signature |
| 24 | Deploy the workflow to authorized staging/VPC | blocker | A1/A3 | image/config digest, health, RLS, storage and network receipts |
| 25 | Prove upgrade, failure, rollback and recovery | blocker | A1/A3 | production-authorized operational receipts |

## Non-negotiable Boundaries

- Stable repeats prove reproducibility, not correctness or qualification.
- Pending review is not a human disposition.
- Empty receipt conservation does not prove review completion.
- A3 may validate transport integrity but may not recompute A2 judgement semantics.
- Peer-branch evidence is not merged-main or production authority.
- Local Store, screenshots and generated OpenAPI are not target deployment receipts.
- Golden Path remains `7/11`; Deployment Acceptance remains `8/17`.
- Current authority remains `integrity_invalid`; production receipts remain `0`.
- `production_ready` remains `false`.
