# A3 Report Center Control Plane Growth - 2026-07-07

## Goal

Move A3 Report Center from local export buttons toward a SaaS control plane that can list hosted reports, summarize lifecycle status, connect each report to manifest evidence, and keep usage/DB/security posture visible.

## What Landed

- Added `services/report/a3_report_center.mjs`.
  - Emits `a3.report_center_index.v1`.
  - Summarizes hosted report count, shareable/expired/revoked/blocked status, total views, manifest readiness, redaction status, usage meters, and SQL migration evidence.
- Extended `services/report/a3_store.mjs`.
  - Adds `getReportCenter(...)`.
  - Adds `report_center` to dashboard API payloads.
- Extended `services/report/a3_api_server.mjs`.
  - Adds `GET /api/a3/reports/center`.
- Extended dashboard wiring.
  - API-backed dashboard loads `report_center`.
  - Sharing a hosted report refreshes Report Center.
  - Report Center shows hosted reports, status, share path, view count, manifest completeness, artifact count, and redaction state.
- Added tests.
  - `tests/a3/report_center_index.test.mjs`
  - Store/API/dashboard wiring assertions.

## Commercial Meaning

A3 now has a clearer paid product path:

- Report export becomes a managed report inventory.
- Hosted reports can be shown as lifecycle objects, not just one-off links.
- Usage ledger and SQL migration evidence are visible beside report artifacts.
- Redaction status and sealed evidence become part of report readiness.
- PR Gate and audit bundle can later point to the same Report Center index and manifest chain.

## Growth-Auditor Notes

### Newly Sellable Capability

Report Center can now act as the hub for customer-facing evidence packets. That is more valuable than another chart because teams need to know which report was shared, whether it is still live, how many times it was viewed, whether it passed redaction, and whether it has a manifest.

### Still Toy-Like Or Incomplete

- The index is backed by the current A3 store, not a real SQL adapter yet.
- Hosted report access still uses report ids, not hashed share tokens.
- View audit is local and redacted; it is not tied to real users, sessions, or IP hashes.
- PR Gate does not yet write the Report Center manifest id into a live GitHub check.
- Billing/usage is read-only and not connected to a billing provider.

### Why Customers Would Pay More

- Engineering leads can use Report Center as release evidence inventory.
- Security reviewers can see redaction and sealed evidence readiness.
- Auditors can later verify report lifecycle and manifest completeness.
- Platform teams can map the same evidence to SQL/self-host readiness.

### Next 20 Growth Points

| ID | Growth point | Owner surface | Concrete next step |
|---|---|---|---|
| RC-01 | Share token lifecycle | API/store | Replace report-id links with hashed share tokens. |
| RC-02 | Denied view audit | API/store | Record expired/revoked/blocked access attempts. |
| RC-03 | Manifest completeness gate | API/UI | Block external share when manifest score is below policy. |
| RC-04 | Report Center list route pagination | API | Add `limit`, `cursor`, status filter, and source filter. |
| RC-05 | Report Center detail route | API/UI | Add one detail payload joining report, manifest, views, redaction, and usage. |
| RC-06 | PR Gate manifest linkage | gate/API | Include report-center manifest id in PR check and PR comment payloads. |
| RC-07 | Audit bundle manifest linkage | report/gate | Add report center index hash to audit bundle verifier inputs. |
| RC-08 | SQL adapter row mapping | store/DB | Persist report center rows once DB tooling is selected. |
| RC-09 | Tenant scoping tests | tests/API | Prove reports cannot cross organization/project scope. |
| RC-10 | Retention policy preview | UI/API | Show purge/retain/legal-hold status without destructive deletion. |
| RC-11 | Report packet presets | UI/API | Add PR review, executive sign-off, security audit, incident replay presets. |
| RC-12 | Export firewall fail-closed publish | API/report | Prevent hosted report creation when residual findings remain. |
| RC-13 | Usage ledger per report | usage/API | Meter report snapshots, views, revocations, and verifier runs by report id. |
| RC-14 | Customer-safe hosted report view | HTML | Add lifecycle banner, manifest summary, and redaction status to hosted HTML. |
| RC-15 | Self-host readiness link | UI/API | Show DB migration and object storage health next to report center status. |
| RC-16 | Report search | UI/API | Search by run id, case id, failure class, source, status, and created date. |
| RC-17 | Report immutable snapshot policy | API/report | Store builder version, source hashes, redaction policy, and payload hash. |
| RC-18 | Reviewer sign-off linkage | UI/API | Attach approvals/waivers to report center manifests. |
| RC-19 | External customer packet | UI/report | Build a minimal customer-facing report packet that hides internal-only fields. |
| RC-20 | Report Center E2E smoke | tests | Cover share -> index -> hosted view -> revoke -> denied hosted view. |

## Safety Boundary

- No `.env.local`, API key, token, cookie, account email, signed URL, or official private source was read or committed.
- No real ReleaseFoundry cloud mutation was performed.
- No real login, team invite, API-key creation/revocation, billing mutation, Trust publish, or destructive retention action was added.
