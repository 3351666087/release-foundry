# A3 Growth Auditor Round 20: Multimodal Disagreement Review

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: A2 v1/v3 compatibility, tenant-scoped import, review queue, reports, and product UI

## Audit Verdict

This round creates one commercially understandable workflow: a safety reviewer can inspect
real A2 model disagreements and repeated-run instability inside the enterprise console.
Evidence is API-backed, durable in the reference stores, exportable, and tenant-scoped.

The workflow is not release authority. Its source is an unmerged A2 peer contract, candidate
binding is not verified, and no authoritative human disposition is present. A3 correctly
keeps production readiness false.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Two-way v1 comparison | implemented | existing integrations remain compatible |
| Two-way v3 repeat comparison | implemented | individual semantic disagreements enter review |
| v3 aggregate instability | implemented | inconsistent repeated model answers are visible |
| Queue receipt conservation | implemented | missing, extra, duplicate, or orphan receipts fail closed |
| Tenant-scoped API and persistence | implemented locally | import/read/audit survive reference-store restart |
| Redacted report export | implemented | JSON, Markdown, and hosted reports include safe review evidence |
| Three-way v2 / four-way v1 | schema observed only | no exact public-safe runtime artifact was available |
| Authoritative human resolution | missing | review queue cannot resolve release state |
| Same-candidate Decision Ledger | missing | current authority remains integrity invalid |
| Production deployment | missing | local implementation is not target-environment proof |

## 24 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Import an A2 v3 artifact from a merged-main service endpoint | blocker | A2/A3 | authenticated response, schema hash, five-level scope |
| 2 | Bind comparison artifact to exact candidate SHA and dataset manifest | blocker | A1/A2 | candidate, dataset, comparison, and ledger hash equality |
| 3 | Add authoritative real-review receipt import | blocker | A2/A3 | reviewer identity hash, sequence, predecessor, disposition |
| 4 | Verify review receipt chain conservation and ordering | blocker | A2/A3 | valid chain and tamper-negative test |
| 5 | Bind final review resolution to the same-candidate Decision Ledger | blocker | A2 | decision record and review-resolution references |
| 6 | Add three-way v2 only after a real public-safe artifact exists | high | A2/A3 | committed artifact, provider states, queue receipts |
| 7 | Add four-way v1 only after a real public-safe artifact exists | high | A2/A3 | committed artifact and six pairwise summaries |
| 8 | Display designated-reference unavailability as its own review reason | high | A2/A3 | reference provider and eligibility-rule receipt |
| 9 | Add reviewer assignment and optimistic locking | high | A3 | assign, conflict, transfer, timeout, and audit receipts |
| 10 | Add dual-review policy for high-severity media findings | high | A2/A3 | two distinct qualified reviewer identities |
| 11 | Add abstain and request-more-evidence workflow | high | A2/A3 | disposition, rationale, evidence request, next state |
| 12 | Add safe media preview through an authorized expiring proxy | high | A1/A3 | object scope, expiry, access audit, no URL export |
| 13 | Persist comparison and review rows in target PostgreSQL with RLS | blocker | A1/A3 | migration, five-level RLS, restart, cross-tenant denial |
| 14 | Add object-custody retention and legal-hold metadata | high | A1/A3 | object version, retention class, hold allow/deny receipts |
| 15 | Paginate and virtualize a 10k-item reviewer queue | high | A3 | p95 latency, bounded memory, stable cursor |
| 16 | Add concurrent import/idempotency stress tests | high | A3 | one durable result per key under parallel retries |
| 17 | Add provider/model/prompt lineage filters | medium | A2/A3 | filter correctness without raw prompt disclosure |
| 18 | Add drift view across model and policy versions | high | A2/A3 | same dataset, versioned comparison, confidence interval |
| 19 | Make unresolved multimodal review a real GitHub required-check blocker | blocker | A2/A3 | tenant App Check and failed-merge denial receipt |
| 20 | Send audited WeCom/DingTalk/Feishu review notifications | medium | A1/A3 | delivery, dedupe, redaction, and retry receipts |
| 21 | Add signed review packet export and verification | high | A3 | manifest, signature, verifier, revoke/expiry audit |
| 22 | Run keyboard, screen-reader, and contrast review | medium | Product/A3 | axe result, focus order, labels, no focus trap |
| 23 | Run reviewer usability testing on repeat versus aggregate concepts | high | Product/A3 | comprehension, task time, error rate, interview notes |
| 24 | Deploy the workflow to authorized staging and capture acceptance | blocker | A1/A2/A3 | identity, image/config digest, migration, health, isolation |

## Highest-value Sequence

1. Same-candidate binding plus authoritative review receipts closes the trust chain.
2. Target PostgreSQL and object custody turn local durability into enterprise evidence.
3. Tenant GitHub required-check enforcement makes unresolved review operationally meaningful.
4. Three-way/four-way support follows real artifacts instead of schema-only speculation.
5. Usability and accessibility validation makes the workflow safe for daily reviewer work.

## Non-negotiable Boundaries

- Queue receipts never become score, failure class, pass/fail, or release authority.
- A3 does not decide which model observation is true.
- An unmerged peer contract is calibration evidence, not production authority.
- Raw model responses, private media, signed URLs, secrets, and account data stay out of exports.
- Cross-tenant access fails closed without revealing case, model, or hash existence.
- The sealed rc.2 release packet remains historical and unchanged.
