# A3 Growth Auditor Round 24: Multimodal Evidence Request Workflow

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: evidence request lifecycle, A1/A2 boundary, persistence, API, report and Review UI

## Verdict

Round 24 closes a concrete product gap between “reviewer claimed a case” and “reviewer has enough evidence
to decide what to do next.” A customer can now request missing evidence, assign its owner lane, track a
deadline, receive hash-only submissions, reject incomplete material, and export the entire metadata chain.

This is commercially useful workflow coordination, but it is not an authoritative evaluation service. An
accepted evidence request is not an A2 human disposition. The round does not change score, pass/fail,
failure class, Decision Ledger, release status, Golden Path, Deployment Acceptance, or production readiness.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Request/create/submit/review lifecycle | implemented locally | reviewers and evidence owners have a repeatable workflow |
| Deadline and overdue projection | implemented locally | SLA state is visible without fabricated timeout events |
| Hash-only evidence intake | implemented | raw media, URLs, identity and secrets fail closed |
| Optimistic concurrency/idempotency | implemented | duplicate and stale writes are controlled |
| Active assignment ownership | implemented locally | only the current reviewer may create or review requests |
| Five-level tenant isolation | contract and local-store tested | cross-tenant reads fail closed |
| Audit/outbox/usage projection | implemented locally | actions can enter enterprise operations pipelines |
| Memory/JSON/SQLite restart | test-proven | local state survives supported restart paths |
| PostgreSQL RLS migrations 023/024 | contract-tested only | target staging execution is still missing |
| Dashboard/JSON/Markdown/Hosted Report | implemented | the request chain is visible and exportable |
| A2 real human disposition | missing | no release decision may be promoted |
| Production identity/storage/signing | missing | local evidence is not production authority |

## 24 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Import one public-safe real A2 human-review receipt | blocker | A2/A3 | disposition schema, predecessor and hash |
| 2 | Validate a complete real review chain | blocker | A2/A3 | duplicate, fork, reorder and tamper tests |
| 3 | Bind terminal review hash to one exact candidate | blocker | A1/A2/A3 | candidate/hash equality across lanes |
| 4 | Consume the same-candidate A2 Decision Ledger | blocker | A2/A3 | verified ledger head and record id |
| 5 | Link requested A1 trace/tool hashes to durable custody | high | A1/A3 | artifact readback, hash and retention receipt |
| 6 | Link requested A2 Judge hashes to durable custody | high | A2/A3 | immutable Judge receipt readback |
| 7 | Add controlled object storage for full evidence sets | high | A1/A3 | tenant scope, checksum, expiry and deletion |
| 8 | Add authorized media preview proxy | high | A1/A3 | no URL export, expiry and access audit |
| 9 | Qualify migrations 023/024 on target PostgreSQL | blocker | A1/A3 | forced RLS, restart and rollback receipts |
| 10 | Prove concurrent reviewers cannot bypass lease ownership | high | A1/A3 | deterministic winner and sanitized losers |
| 11 | Add SLA escalation and overdue worker | high | A1/A3 | retry, dedupe, dead-letter and audit evidence |
| 12 | Add WeCom/DingTalk/Feishu notifications | medium | A1/A3 | signed delivery and retry receipts |
| 13 | Add reviewer qualification checks | high | A1/A3 | directory-backed allow/deny evidence |
| 14 | Add conflict-of-interest checks | high | A1/A3 | relationship policy and denial receipt |
| 15 | Add dual-review policy for high-risk media | high | A2/A3 | two distinct qualified review receipts |
| 16 | Add cursor pagination for large request histories | medium | A3 | stable sort and 10k-row load test |
| 17 | Add accessible keyboard and screen-reader workflow | medium | A3 | zero critical axe findings and focus report |
| 18 | Add same-origin CSRF protection for browser mutations | blocker | A1/A3 | valid and invalid session/CSRF tests |
| 19 | Bind Audit Archive signing to tenant KMS/HSM | blocker | A1/A3 | signer identity, key version and revocation |
| 20 | Make unresolved required evidence fail a GitHub App Check | blocker | A1/A2/A3 | tenant App identity and real merge denial |
| 21 | Add GitLab and signed-webhook parity | medium | A1/A3 | live sandbox readback and replay defense |
| 22 | Measure request age and completion cohorts | medium | Product/A3 | privacy-safe metric definitions and report |
| 23 | Rebuild Trusted Spine after exact candidate convergence | blocker | A1/A2/A3 | fresh A1/A2/A3 hashes in one spine |
| 24 | Deploy and verify the workflow in target VPC | blocker | A1/A3 | identity, DB, storage, KMS, health and rollback receipts |

## Non-negotiable Boundaries

- `accepted` means supplemental evidence accepted, not human disposition accepted.
- Hash presence does not prove the referenced evidence is true or correctly interpreted.
- A3 may verify its event-chain integrity but may not recompute A2 judgement semantics.
- Migration SQL is not evidence that target PostgreSQL has executed it.
- Local Store, local signatures and screenshots are not production deployment receipts.
- Golden Path remains `7/11`; Deployment Acceptance remains `8/17`.
- Current authority remains `integrity_invalid`; production receipts remain `0`.
- `production_ready` remains `false`.
