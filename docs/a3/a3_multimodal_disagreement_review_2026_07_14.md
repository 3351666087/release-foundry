# A3 Multimodal Disagreement Review

- Date: 2026-07-14
- Main authority: `ccf6ce5`
- A1 peer ref inspected: `2307231`
- A2 peer ref inspected: `564d4b0`
- Evidence level: `peer_branch_contract_not_merged`
- Production readiness changed: `false`

## 1. Beginner Summary

A media judge can look at an image, audio file, document, or video and decide whether it
contains a risk. Two judge models may disagree. One model may also change its answer when the
same evidence is evaluated several times.

This round turns those disagreements into a real A3 reviewer workflow:

1. A2 produces a public-safe comparison and queue receipts.
2. A3 validates the evidence, hashes, counts, tenant scope, and non-authoritative boundary.
3. A3 stores the comparison and shows the disagreement to a human reviewer.
4. A3 exports the same evidence in JSON, Markdown, and a shareable report.
5. A3 does not decide which model is correct and does not change the release decision.

The dashboard now shows two kinds of review item:

- `repeat`: one concrete model comparison, such as repeat number 2;
- `aggregate`: a summary showing that a model changed its answer across repeats.

## 2. A1 and A2 Calibration

The round re-fetched all active refs before implementation:

| Ref | Observed state | A3 use |
|---|---|---|
| `origin/main` | `ccf6ce5` | authoritative merged baseline |
| A1 development | `2307231` | identity, tenant scope, runtime evidence, and service-account boundary |
| A2 development | `564d4b0` | non-main multimodal comparison calibration only |

A2 advanced while this round was in progress. The latest branch adds bounded provider
execution, pricing and budget policy, three-way/four-way comparison schemas, designated
reference handling, and exact release identity checks.

A3 consumed one real public-safe A2 v3 evidence artifact from:

```text
docs/evidence/a2_multimodal_cross_provider_comparison_round41_unstable.json
```

The A3 copy is:

```text
fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json
```

It contains no raw provider response or media. It records 6 repeat comparisons, 2 aggregate
comparisons, 2 repeat-level semantic disagreements, 2 internally unstable aggregates, and 4
human-review queue receipts.

The older two-way v1 fixture remains covered for backward compatibility. A3 does not yet
accept A2 three-way v2 or four-way v1 because no generated public-safe artifact using those
exact schema versions was found at the inspected peer ref. Schema presence alone is not
treated as runtime evidence.

## 3. Data Flow

```text
A2 public-safe comparison
  -> strict schema and safety validation
  -> five-level tenant scope binding
  -> idempotent A3 import receipt
  -> Memory / JSON / SQLite persistence
  -> metadata-only audit event and event outbox
  -> reviewer queue API
  -> Dashboard review page
  -> redacted JSON / Markdown / hosted report
```

## 4. Validation and Compatibility

The adapter supports:

| Upstream contract | State | Important behavior |
|---|---|---|
| `a2.multimodal_cross_provider_comparison.v1` | supported | one comparison per case and one queue receipt per required artifact |
| `a2.multimodal_cross_provider_comparison.v3` | supported | repeats, aggregate instability, comparison artifact binding, and receipt conservation |
| `a2.multimodal_three_way_comparison.v2` | observed schema only | wait for a real public-safe artifact before implementation |
| `a2.multimodal_four_way_comparison.v1` | observed schema only | wait for a real public-safe artifact before implementation |

The validator rejects:

- missing organization, tenant, workspace, project, or environment scope;
- `release_authority=true` anywhere in the comparison or queue receipts;
- raw model payload declarations, URLs, secrets, account paths, or emails;
- malformed or duplicate SHA-256 identities;
- incorrect repeat or aggregate summary counts;
- orphan, duplicate, missing, or over-produced queue receipts;
- an aggregate marked internally unstable without mixed repeat evidence;
- unsupported comparison or review states.

For v3, queue receipt conservation means every review-required repeat or aggregate has exactly
one matching receipt, and no receipt exists without a matching review item.

## 5. API, Storage, and Audit

Protected routes:

```text
POST /api/a3/import/a2-multimodal-comparison
GET  /api/a3/review/multimodal-queue
```

The import requires a server-verified principal, `project:ingest`, five-level scope, and an
`Idempotency-Key`. The read requires `release:review`. Cross-tenant reads fail as 404 without
revealing model names, case IDs, or hashes.

The imported evidence survives Memory, JSON-file, and SQLite stores. Successful imports emit
a metadata-only audit record and event-outbox envelope. Raw model payloads, media bytes, signed
URLs, provider secrets, and share tokens are not placed in those records.

OpenAPI runtime parity is `60/60`. API Reference v9 documents v1/v3 support and leaves
three-way/four-way support explicitly pending.

## 6. Product and Report Experience

The Chinese-first Review page displays:

- total repeat and aggregate comparisons;
- semantic disagreements and open review count;
- the two provider/model identities;
- repeat number or aggregate scope;
- each model's observed risk or repeat instability;
- reviewer queue state;
- a visible statement that the queue cannot change release state.

Machine states are translated into customer language in the UI. API values remain stable for
clients. The queue is also included in JSON, Markdown, and shareable report payloads after the
export redaction firewall.

Screenshots:


Both screenshots were visually inspected. The desktop list remains scannable and the 390 x
844 layout has no document-level horizontal overflow or overlapping controls.

## 7. Authority Boundary

This round does not prove or change any release authority:

```text
Golden Path: 7/11
Deployment Acceptance: 8/17
Current authority: integrity_invalid
Current A2 decision: unknown
Historical A2 decision: block
Production verified receipts: 0
Production ready: false
```

The queue receipt is only evidence that a review is required. A release-state change still
requires an authoritative human-review result and a Decision Ledger bound to the exact same
candidate. The A2 Round 48 binding receipt remains blocked because A1, A2, and A3 do not expose
one shared candidate identity.

## 8. Verification

Completed local checks:

```text
node --test tests/a3/*.test.mjs
python -B -m unittest discover -s tests/a2
npm.cmd run typecheck --prefix apps/webapp
npm.cmd run build --prefix apps/webapp
npx.cmd playwright test
node services/report/a3_openapi_runtime_parity.mjs docs/a3/openapi/a3_commercial_api.openapi.json
python scripts/cl_guard.py hygiene
python scripts/cl_guard.py commercial
npm.cmd audit --omit=dev
npm.cmd audit --omit=dev --prefix apps/webapp
git diff --check
```

Results:

- A3 Node: 476 passed, 1 explicit target-PostgreSQL opt-in skip, 0 failed;
- current-main A2: 186 tests passed;
- Playwright: 42/42 passed;
- Next.js: TypeScript passed and 15 static pages built;
- OpenAPI: 60/60 runtime operations documented;
- CL hygiene: 0 findings;
- Commercial CL: 0 blockers and 0 advisories;
- root and Webapp production npm audits: 0 vulnerabilities.

## 9. Next Production Step

The next useful step is not another mock card. It is an authoritative review-result import
bound to the same candidate as A1 execution evidence and the A2 Decision Ledger. After A2
publishes real three-way/four-way artifacts, A3 can generalize the provider list without
inventing evidence.
