# A3 Growth Auditor Round 26: Multimodal Provider Readiness

- Date: 2026-07-14
- Audit mode: fail-closed commercial audit
- Scope: A2 Round 51 availability and phase latency, A3 intake, persistence, API, reports, OpenAPI and Delivery UI

## Verdict

Round 26 closes an observability gap: the product can now explain why installed local multimodal models are still
not usable. It preserves the real evidence that 29 of 30 attempts failed or timed out, zero outputs were eligible,
and all four structured-output profiles failed. The warm path is faster, but the output is still invalid.

This is a commercially useful diagnostic surface, not Provider health, capacity, quality qualification, or release
authority. A1 retains production routing and health authority, A2 retains evaluation and qualification authority,
and A3 only validates, stores, displays, exports, and coordinates the evidence.

## Capability Classification

| Capability | State | Commercial meaning |
|---|---|---|
| Atomic availability + latency intake | implemented locally | partial evidence cannot create a misleading ready state |
| Exact nested allowlists | implemented | unknown fields and unsafe material fail closed |
| Count and latency conservation | implemented | malformed diagnostics cannot enter the console |
| Provider/model binding | implemented | phase probe cannot be attached to another model silently |
| Five-level tenant scope | contract-tested | cross-tenant reads fail closed |
| Header-only idempotency | implemented | retries are safe and changed payloads conflict |
| Memory/JSON/SQLite durability | test-proven | local restart preserves diagnostics |
| Audit/outbox/usage | implemented locally | imports enter enterprise operations evidence |
| JSON/Markdown/Hosted Report | implemented | public-safe diagnostic evidence is portable |
| Strict OpenAPI | `69/69` parity | clients receive typed contracts and authority metadata |
| API Reference v15 | implemented | operators can inspect import/read examples and limitations |
| Chinese-first responsive Delivery UI | implemented | blocked readiness is understandable on desktop/mobile |
| A1 production routing/health evidence | missing | local diagnosis cannot prove production operations |
| A2 Provider qualification | blocked | zero eligible outputs and invalid structured responses |
| Production identity/storage/deployment | missing | local proof is not staging/VPC acceptance |

## 26 Executable Next Growth Points

| # | Executable next step | Priority | Owner | Proof required |
|---:|---|---|---|---|
| 1 | Repair structured-output validity for all four profiles | blocker | A2 | 4/4 valid schema receipts with immutable hashes |
| 2 | Re-run the same 30-case availability comparison | blocker | A2 | materially lower failure/timeout rate and non-zero eligible outputs |
| 3 | Define the authoritative A2 Provider qualification threshold | blocker | A2 | versioned policy hash, metrics and pass/fail rationale |
| 4 | Produce an A2-qualified retained calibration | blocker | A2 | qualification state `qualified` with complete evidence |
| 5 | Add A1 production Provider health receipt schema | blocker | A1 | workload identity, region, endpoint class, health and expiry |
| 6 | Add A1 capacity and saturation evidence | high | A1 | concurrency, queue depth, throughput, p95/p99 and error budget |
| 7 | Add A1 routing and failover evidence | blocker | A1 | primary/backup transition, circuit breaker and recovery receipt |
| 8 | Bind diagnostics to one exact candidate ID | blocker | A1/A2 | matching Git SHA, run, case set, model and policy hashes |
| 9 | Bind qualified evidence to the same-candidate Decision Ledger | blocker | A2/A3 | chain-valid record and ledger head hash |
| 10 | Rebuild the Trusted Spine after candidate convergence | blocker | A1/A2/A3 | current integrity verified with no scope mismatch |
| 11 | Publish exact non-empty human-review receipt schema | blocker | A2 | closed schema, signer, predecessor and disposition rules |
| 12 | Complete one real multimodal human review | blocker | A2/A3 | public-safe receipt, conservation and terminal disposition |
| 13 | Add controlled media preview to the Provider incident view | high | A1/A3 | tenant auth, short expiry, checksum and access audit |
| 14 | Add per-phase regression charts across releases | medium | A3 | candidate-bound time series with privacy-safe retention |
| 15 | Add Provider incident clustering | medium | A2/A3 | timeout, invalid output, load, prompt eval and token eval taxonomy |
| 16 | Add latency budget policy without treating it as quality | high | A1/A2/A3 | separate operational and evaluation gates with distinct owners |
| 17 | Add Provider health alert deduplication and escalation | medium | A1/A3 | retry, dead letter, incident owner and notification receipts |
| 18 | Add WeCom, DingTalk and Feishu incident notifications | medium | A1/A3 | signed delivery, retry and audit receipts |
| 19 | Qualify persistence on target PostgreSQL forced RLS | blocker | A1/A3 | migration, cross-scope denial, restart and rollback receipts |
| 20 | Move evidence artifacts to controlled object storage | blocker | A1/A3 | checksum, scope, retention, deletion and recovery |
| 21 | Bind hosted operator identity to SSO/MFA | blocker | A1/A3 | session, step-up, CSRF, role and audit evidence |
| 22 | Publish a tenant-bound GitHub App Check for Provider blockers | blocker | A1/A2/A3 | installation identity and real merge denial |
| 23 | Add SLA and cost views for domestic/private deployment | medium | A1/A3 | CNY cost, quota, overage and procurement contract |
| 24 | Export Provider readiness in the next signed Audit Bundle | high | A3 | candidate-bound manifest and tenant KMS signature |
| 25 | Deploy the workflow to authorized staging/VPC | blocker | A1/A3 | image/config digest, network, health, RLS and storage receipts |
| 26 | Prove upgrade, fault injection, rollback and recovery | blocker | A1/A3 | authorized operational receipts from the target environment |

## Other Product Angles

1. **Developer platform:** expose machine-readable diagnostics through SDK clients and webhook events without raw
   Provider output.
2. **FinOps:** keep warmup, token evaluation and failure retry cost separate so buyers can identify wasted spend.
3. **Procurement:** compare local/private/cloud Provider options using verified cost, residency and SLA evidence.
4. **Incident response:** connect a blocked Provider profile to affected runs, cases, media evidence and owners.
5. **Trend analysis:** show whether a new candidate improves validity and availability without hiding confidence
   intervals or changing A2 policy.
6. **China-first operations:** add domestic notification and payment workflows only after provider qualification and
   business approvals are proven.
7. **Privacy:** retain hashes and aggregate metrics by default; raw media must remain behind explicit tenant access.
8. **Accessibility:** keep status meaning available as text and not color alone on desktop, mobile, and mini program.

## Non-negotiable Boundaries

- Installed does not mean ready.
- Faster warm latency does not mean valid output or qualified quality.
- One completed attempt out of 30 is not operational health.
- A3 may validate transport integrity but may not recompute A2 judgement or qualification.
- Peer-branch evidence is not merged-main or production authority.
- Local Store, SQLite, screenshots and OpenAPI are not target deployment receipts.
- A1 `f3071aa` credential-link coordinator is proposed and non-client-callable.
- Golden Path remains `7/11`; Deployment Acceptance remains `8/17`.
- Current authority remains `integrity_invalid`; production receipts remain `0`.
- `production_ready` remains `false`.
