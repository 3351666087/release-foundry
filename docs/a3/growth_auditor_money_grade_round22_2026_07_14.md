# A3 Growth Auditor Round 22: Signed Review Assignment Packet

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: assignment history, packet integrity, Gate CLI custody, signed archive, report/UI and accessibility

## Verdict

This round closes Round 21 item 17 and the keyboard portion of item 18. Reviewer assignment history
is now a reproducible, metadata-only, tamper-evident review record that can enter the existing signed
Audit Archive. It improves compliance handoff, reviewer accountability, incident reconstruction, and
self-host evidence export without inventing a human disposition.

This is not production signing. The committed archive uses a local ephemeral Ed25519 key and declares
`self_signed_local_key_not_sso_bound`. A production claim still requires tenant-bound identity, KMS/HSM
custody, target storage, retention, revocation and authorized environment receipts.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Event hash and strict field validation | implemented | corrupted local assignment rows fail closed |
| Contiguous history and tenant binding | implemented | reorder, gap, subject and cross-scope errors are detected |
| Review assignment packet CLI | implemented | operators can build and verify portable redacted packets |
| Gate CLI review-record ingestion | implemented | only verified packet files enter the bundle |
| Audit Bundle hash and custody chain | implemented locally | exact packet file is bound to release evidence |
| Ed25519 Audit Archive | implemented locally | tampering after seal is detected |
| Dashboard/report/registry projection | implemented | operators and auditors see packet readiness |
| Keyboard-expandable history | implemented | the core history disclosure is keyboard reachable |
| Production signer identity | missing | local self-signing is not enterprise trust |
| Real A2 human disposition | missing | assignment history cannot resolve model truth |

## 22 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Import a public-safe real A2 human-review receipt | blocker | A2/A3 | real identity class, disposition, sequence and predecessor |
| 2 | Validate duplicate, fork, reorder and broken-predecessor A2 review chains | blocker | A2/A3 | positive and negative chain receipts |
| 3 | Bind packet terminal review hash to the exact candidate | blocker | A1/A2/A3 | run, comparison, packet and candidate hash equality |
| 4 | Consume a same-candidate A2 Decision Ledger | blocker | A2/A3 | verified head hash, record id and chain |
| 5 | Add dual-review policy for high-severity media | high | A2/A3 | two distinct qualified reviewer aliases and policy result |
| 6 | Add reviewer qualification and conflict-of-interest checks | high | A1/A2/A3 | directory-backed allow/deny receipts |
| 7 | Add request-more-evidence tasks with deadlines | high | A2/A3 | child-task state, timeout, audit and disposition binding |
| 8 | Add an A1-backed tenant-safe reviewer transfer picker | high | A1/A3 | scoped aliases, loading/empty/failed/denied states |
| 9 | Add same-origin CSRF-bound browser assignment mutations | blocker | A1/A3 | CSRF allow/deny, session binding and audit receipts |
| 10 | Run migrations 021/022 in authorized staging PostgreSQL | blocker | A1/A3 | forced RLS, restart, isolation and rollback receipts |
| 11 | Prove one-winner parallel claims with real DB transactions | high | A1/A3 | deterministic winner and sanitized 409 losers |
| 12 | Add lease cleanup, SLA escalation and dead-letter worker | high | A1/A3 | retries, recovery, idempotency and outbox evidence |
| 13 | Add cursor pagination and stable sort for 10k queue rows | high | A3 | load test, bounded memory and cursor correctness |
| 14 | Add workload, age, severity and assignment-state filters | medium | A3 | filter tests and no foreign-tenant count leakage |
| 15 | Add audited WeCom, DingTalk and Feishu assignment notifications | medium | A1/A3 | signed delivery receipts, retry and secret redaction |
| 16 | Add an expiring authorized media preview proxy | high | A1/A3 | object scope, expiry, access audit and no URL export |
| 17 | Bind packet signatures to tenant KMS/HSM or workload identity | blocker | A1/A3 | signer identity, key version, rotation and revocation receipt |
| 18 | Add axe accessibility scans and reduced-motion checks | medium | A3 | zero critical axe issues and keyboard/focus report |
| 19 | Measure completion time, expiry and reassignment rates | medium | Product/A3 | privacy-safe cohort and usage event definitions |
| 20 | Make unresolved required review fail a tenant GitHub App Check | blocker | A1/A2/A3 | custom App identity and failed-merge denial |
| 21 | Rebuild Trusted Spine only after exact candidate convergence | blocker | A1/A2/A3 | fresh A1, A2 and A3 artifact hashes in one spine |
| 22 | Deploy and verify packet custody in target VPC | blocker | A1/A3 | DB, object storage, KMS, retention, health and rollback receipts |

## Non-negotiable Boundaries

- An assignment packet is not a human disposition.
- A packet root hash is not a production signature.
- A local self-signed archive is not a tenant-bound KMS/HSM receipt.
- A3 never recomputes A2 risk, score, pass/fail, failure class, Decision Ledger or release readiness.
- Raw identity, model payload, private media, signed URL, key, token and cookie remain excluded.
- Golden Path `7/11`, Deployment Acceptance `8/17`, production receipts `0`, and production ready false remain unchanged.
