# A3 Commercial Evidence Coverage - 2026-07-09

ANCHOR: A3_COMMERCIAL_EVIDENCE_COVERAGE

This artifact records the minimum customer-safe commercial evidence packet A3 should be able to explain: A1 runner evidence, A2 judge evidence, and A3 report, review, GitHub, billing, audit, and redaction evidence. It is intentionally a redacted coverage artifact, not a new dashboard feature or hosted provider integration.

Fixture:

- `fixtures/a3/p3/a3_commercial_evidence_coverage.redacted.json`

Test:

- `tests/a3/a3_commercial_evidence_coverage.test.mjs`

ANCHOR: EVIDENCE_BINDINGS

Required evidence families:

- A1 RunResult: run id, case state, trace ids, tool-call summaries, observation ids, and usage counts.
- A2 GradeResult: pass state, score, failure class, threshold, judge version, and calibration references.
- A3 Report: report export and Report Center manifest evidence.
- A3 Review: reviewer workflow, exception review, and approval readiness evidence.
- A3 GitHub: check readback and PR comment readback evidence.
- A3 Billing: usage ledger and billing readiness evidence.
- A3 Audit: audit bundle index and verification evidence.
- A3 Redaction: export firewall and generated artifact scan evidence.

A3 remains downstream-only here. The packet binds evidence produced by A1 and A2, then packages it into A3-owned commercial surfaces; it does not alter A1 runner behavior or A2 judge scoring.

ANCHOR: ARTIFACT_TYPES

The fixture declares 11 artifact types:

- `a1_run_result`
- `a2_grade_result`
- `a3_report`
- `a3_report_center_manifest`
- `a3_review_workflow`
- `a3_github_check_readback`
- `a3_github_pr_comment_readback`
- `a3_billing_usage_ledger`
- `a3_audit_bundle_index`
- `a3_redaction_firewall`
- `a3_commercial_evidence_packet`

The commercial claim is that A3 can assemble a buyer-facing release intelligence packet from these artifact types while preserving source boundaries and redaction guarantees.

ANCHOR: TENANT_AUTH_RBAC_USAGE_AUDIT_REDACTION

Tenant/auth/RBAC/usage/audit/redaction declaration:

- Tenant: every durable hosted row must carry `organization_id`, `project_id`, and `release_id`; cross-tenant reads default to empty or denied.
- Auth: this is local redacted evidence only; hosted refresh or publish requires authenticated service identity.
- RBAC: owner, admin, developer, reviewer, auditor, and billing admin roles are declared, with read-only coverage until hosted RBAC exists.
- Usage: meters are counts for coverage exports, report packets, GitHub readback receipts, billing summary views, and redaction scans.
- Audit: append-only events are required for coverage generation, export, and verification.
- Redaction: raw values, credentials, customer emails, local account paths, and signed media links are not allowed in this artifact.

ANCHOR: ACCEPTANCE

Run:

```text
node --test tests/a3/a3_commercial_evidence_coverage.test.mjs
```

The test verifies:

- the fixture is valid JSON and uses `a3.commercial_evidence_coverage.v1`
- 8+ unique artifact types are present
- A1 RunResult, A2 GradeResult, A3 Report, A3 Review, A3 GitHub, A3 Billing, A3 Audit, and A3 Redaction families are bound
- tenant/auth/RBAC/usage/audit/redaction sections are present
- safety flags keep raw values and provider mutations disabled
- the fixture and doc stay secret-free under the local generated-artifact scan patterns
