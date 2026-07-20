# A3 Growth Auditor Round 23: Three-provider Review Intake

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: A2 Round 50 three-way v2 intake, review projection, persistence, report, UI and evidence

## Verdict

This round closes the previously explicit A3 wait condition for a real public-safe A2 three-way v2
artifact. A reviewer can now see all three provider observations in one tenant-scoped workflow,
assign the disagreement, and export metadata-only evidence without A3 fabricating model identity,
human disposition, score, or release authority.

Commercially, this reduces the gap between a two-model demo and a provider-neutral enterprise review
console. It does not close authoritative human review, candidate convergence, production identity,
target deployment, or production signing.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Three-way v2 strict validator | implemented | malformed provider/state/receipt data fails closed |
| Real Round 50 public-safe calibration | implemented as redacted projection | UI and adapter follow an observed A2 artifact |
| Tenant-scoped import and read | implemented locally | service accounts can ingest; reviewers can read |
| Assignment compatibility | implemented locally | existing lease/audit workflow works for three providers |
| Memory and SQLite restart durability | implemented locally | comparison and assignment survive local restart |
| Dynamic three-provider UI | implemented | no left/right-only rendering assumption |
| JSON/Markdown/Hosted Report | implemented | provider observations reach customer evidence exports |
| Production provider identity | missing | provider keys are not a signed directory binding |
| Real human disposition | missing | queue state remains pending |
| Exact shared candidate | missing | no valid same-candidate Trusted Spine |

## 23 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Import one public-safe real A2 human-review receipt | blocker | A2/A3 | disposition, predecessor, identity class and hash |
| 2 | Validate duplicate, fork, reorder and broken review chains | blocker | A2/A3 | positive and negative chain fixtures |
| 3 | Bind terminal review hash to the exact shared candidate | blocker | A1/A2/A3 | candidate/hash equality across all lanes |
| 4 | Consume a same-candidate A2 Decision Ledger | blocker | A2/A3 | verified ledger head and record id |
| 5 | Import the full 74-case artifact through controlled object storage | high | A1/A3 | object hash, retention, readback and pagination |
| 6 | Add cursor pagination and stable sorting for 10k review rows | high | A3 | load test and cursor correctness |
| 7 | Add a signed provider/model identity projection | high | A1/A2/A3 | provider key to model/version evidence binding |
| 8 | Add request-more-evidence tasks with deadlines | high | A2/A3 | task state, response hash, timeout and audit |
| 9 | Add dual-review policy for high-severity media | high | A2/A3 | two distinct qualified reviewer receipts |
| 10 | Add reviewer qualification and conflict-of-interest checks | high | A1/A3 | directory-backed allow/deny evidence |
| 11 | Add same-origin CSRF-bound browser review mutations | blocker | A1/A3 | CSRF/session allow and deny tests |
| 12 | Qualify migrations 021/022 in authorized staging PostgreSQL | blocker | A1/A3 | forced RLS, restart, rollback and isolation |
| 13 | Prove one-winner parallel assignment claims in PostgreSQL | high | A1/A3 | deterministic winner and sanitized 409 losers |
| 14 | Add lease cleanup, SLA escalation and dead-letter recovery | high | A1/A3 | worker retries, idempotency and outbox receipts |
| 15 | Add expiring authorized media-preview proxy | high | A1/A3 | scope, expiry, access audit and no URL export |
| 16 | Send audited WeCom/DingTalk/Feishu review notifications | medium | A1/A3 | signed delivery receipts and retry evidence |
| 17 | Make unresolved required review fail a tenant GitHub App Check | blocker | A1/A2/A3 | custom App identity and merge denial |
| 18 | Add GitLab status and generic signed webhook parity | medium | A1/A3 | live sandbox readback and replay protection |
| 19 | Bind Audit Archive signing to tenant KMS/HSM identity | blocker | A1/A3 | signer id, key version, rotation and revocation |
| 20 | Run axe, keyboard, reduced-motion and screen-reader checks | medium | A3 | zero critical axe findings and focus report |
| 21 | Measure three-provider queue latency and completion cohorts | medium | Product/A3 | privacy-safe usage definitions and report |
| 22 | Rebuild Trusted Spine only after exact candidate convergence | blocker | A1/A2/A3 | fresh A1/A2/A3 hashes in one spine |
| 23 | Deploy and verify review custody in target VPC | blocker | A1/A3 | identity, DB, storage, KMS, health and rollback receipts |

## Non-negotiable Boundaries

- Three provider observations are not three independent ground truths.
- A queue receipt is not a human disposition.
- Provider keys are not verified model identity.
- A redacted representative projection is not the complete 74-case upstream artifact.
- A3 never recomputes A2 score, pass/fail, failure class, Decision Ledger, or release readiness.
- Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, and production ready false remain unchanged.
