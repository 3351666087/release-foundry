# P3 Report Center Manifest Contract - 2026-07-07

Author: ReleaseFoundry A3 Report Center Manifest Worker
Scope: documentation contract only. This pass does not change runtime code, service code, dashboard code, fixtures, schemas, credentials, or secret-bearing files. It defines the manifest shape the Report Center should use to list, verify, share, and retain release-evidence artifacts.

ANCHOR: A3_REPORT_CENTER_MANIFEST_CONTRACT

## 1. Contract Status

The Report Center manifest is the human and machine index for every export, share, gate, audit, replay, reviewer, and usage artifact that belongs to one A3 release-evidence packet.

Required schema anchor:

- `a3.report_center_manifest.v1`

Related existing or planned schemas:

- `a3.export_report.v1`
- `a3.generated_artifact_manifest.v1`
- `a3.audit_bundle_index.v1`
- `a3.shareable_report.v1`
- `a3.gate_cli.v1`
- `a3.github_check_run.v1`
- `a3.release_workflow.v1`
- `a3.incident_replay_queue.v1`
- `a3.review_board.v1`
- `a3.usage_ledger.v1`

The manifest does not replace generated artifact hashing or audit bundle verification. It sits above them and gives Report Center one stable catalog of artifacts, lifecycle state, redaction status, custody links, and usage events.

## 2. Manifest Envelope

ANCHOR: MANIFEST_ENVELOPE

Required top-level fields:

| Field | Purpose |
|---|---|
| `schema_version` | Must be `a3.report_center_manifest.v1`. |
| `manifest_id` | Stable id for the Report Center packet manifest. |
| `organization_id` | Tenant boundary for SQL-backed implementations. |
| `project_id` | Project boundary for SQL-backed implementations. |
| `release_id` | A3 release, PR, or candidate id represented by the packet. |
| `run_id` | Primary A1/A3 run id when one run anchors the packet. |
| `head_sha` | Git head SHA or `local-demo-head-sha` for local-only evidence. |
| `source_snapshot_id` | Immutable report snapshot id used by generated exports and hosted report. |
| `source_payload_hashes` | Hashes of imported A1/A2/A3 evidence inputs. |
| `generated_artifact_manifest_id` | Link to `a3.generated_artifact_manifest.v1` when available. |
| `audit_bundle_id` | Link to `a3.audit_bundle_index.v1` when available. |
| `redaction_policy_version` | Policy used before any artifact is published or shared. |
| `artifacts` | Ordered artifact records described below. |
| `lifecycle_summary` | Counts by lifecycle state and blocking reason. |
| `safety` | Secret, path, signed URL, and CSV-injection safety summary. |
| `created_at` | Manifest creation timestamp. |
| `updated_at` | Last manifest update timestamp. |

## 3. Artifact Registry

ANCHOR: ARTIFACT_REGISTRY

Every artifact record must include these fields:

| Field | Required | Purpose |
|---|---:|---|
| `artifact_id` | yes | Stable snake-case id used by tests, SQL rows, audit events, and UI actions. |
| `artifact_name` | yes | Human display name. |
| `artifact_kind` | yes | One of `export`, `hosted_report`, `github`, `audit`, `replay`, `review`, or `usage`. |
| `schema_version` | yes | Contract or payload schema emitted by the artifact. |
| `content_type` | yes | MIME type or durable logical type. |
| `format` | yes | User-facing format: JSON, Markdown, CSV, PDF/print, HTML, GitHub Check, PR comment, bundle, board, or ledger. |
| `producer` | yes | Builder or workflow that creates the artifact. |
| `source_snapshot_id` | yes | Snapshot or run source used to build the artifact. |
| `content_hash` | yes for generated files | SHA-256 of the generated body or `pending` before generation. |
| `byte_size` | yes for generated files | Generated body size or `pending` before generation. |
| `workspace_path` | optional | Workspace-relative path only. No local absolute paths. |
| `hosted_url_path` | optional | Product URL path for hosted artifacts. No raw share tokens in stored manifest rows. |
| `redaction_status` | yes | `passed`, `blocked`, `not_applicable`, or `pending`. |
| `verification_status` | yes | `not_required`, `pending`, `passed`, `failed`, or `stale`. |
| `lifecycle_state` | yes | Current state from the lifecycle state list. |
| `created_at` | yes | Artifact creation timestamp or planned timestamp. |
| `published_at` | optional | When the artifact became visible outside local generation. |
| `expires_at` | optional | Required for externally shared hosted report links. |
| `revoked_at` | optional | Set when a hosted artifact or share link is revoked. |
| `retention_policy` | yes | Retention class such as `release_evidence_365d`, `audit_7y`, or `local_demo`. |
| `audit_event_ids` | yes | Audit events created for build, scan, publish, share, view, revoke, verify, or purge. |
| `usage_event_ids` | optional | Usage ledger rows caused by the artifact. |

## 4. Required Artifact Names

ANCHOR: REQUIRED_ARTIFACT_NAMES

The manifest must preserve these artifact ids and names:

| `artifact_id` | `artifact_name` | Kind | Format | Schema anchor | Lifecycle notes |
|---|---|---|---|---|---|
| `json_report` | JSON report | `export` | JSON | `a3.export_report.v1` | Generated from the same source snapshot as every other report output. |
| `markdown_report` | Markdown report | `export` | Markdown | `a3.export_report_markdown.v1` | Human-readable release evidence. |
| `csv_export` | CSV export | `export` | CSV | `a3.export_report_csv.v1` | Must pass CSV formula-injection hardening before publish. |
| `pdf_print_report` | PDF/print report | `export` | PDF/print | `a3.export_report_print.v1` | May be generated as PDF bytes or print-ready HTML evidence. |
| `hosted_report` | Hosted report | `hosted_report` | HTML | `a3.shareable_report.v1` | Must support expiry, revocation, and view audit before customer sharing. |
| `pr_comment_markdown` | PR comment Markdown | `github` | PR comment | `a3.pr_comment_markdown.v1` | Must include a stable marker for update-in-place behavior. |
| `github_check_run` | GitHub check run | `github` | GitHub Check | `a3.github_check_run.v1` | Must name conclusion, annotations, details URL, and merge-blocking state. |
| `audit_bundle_index` | Audit bundle index | `audit` | bundle | `a3.audit_bundle_index.v1` | Must carry bundle root hash and chain-of-custody events. |
| `replay_pack` | Replay pack | `replay` | bundle | `a3.incident_replay_queue.v1` | Failed cases first, with trace/tool-call/judge evidence links. |
| `reviewer_board` | Reviewer board | `review` | board | `a3.review_board.v1` | Reviewer lanes, missing evidence, waiver state, and approval readiness. |
| `usage_ledger` | Usage ledger | `usage` | ledger | `a3.usage_ledger.v1` | Append-only source for usage and quota evidence. |

## 5. Lifecycle Fields And States

ANCHOR: LIFECYCLE_FIELDS

Each artifact record must expose lifecycle fields directly, even when an implementation stores some values in SQL tables.

Required lifecycle fields:

- `lifecycle_state`
- `created_at`
- `updated_at`
- `created_by`
- `published_at`
- `expires_at`
- `revoked_at`
- `viewed_at`
- `verified_at`
- `purged_at`
- `retention_policy`
- `blocking_reason`
- `audit_event_ids`

Allowed lifecycle states:

- `planned`
- `queued`
- `building`
- `redaction_scanning`
- `redaction_blocked`
- `generated`
- `published`
- `shared`
- `viewed`
- `revoked`
- `expired`
- `verified`
- `retained`
- `purged`
- `failed`

Lifecycle invariants:

- `published`, `shared`, and `viewed` require `redaction_status=passed`.
- `shared` hosted reports require `expires_at` and a share-link audit event.
- `revoked` requires `revoked_at` and `report.share_link_revoked`.
- `expired` must not render the report body to external viewers.
- `verified` requires either a matching content hash or a passing audit bundle verification result.
- `purged` requires a retention audit event and must not erase the original audit event chain.

## 6. Surface Contracts

ANCHOR: SURFACE_CONTRACTS

Report exports:

- `json_report`, `markdown_report`, `csv_export`, and `pdf_print_report` are generated from one immutable `source_snapshot_id`.
- Each generated file records `content_hash`, `byte_size`, `content_type`, `workspace_path`, `redaction_status`, and `verification_status`.
- CSV artifacts must neutralize spreadsheet formula prefixes before `published`.

Hosted report:

- `hosted_report` links to `a3.shareable_report.v1`.
- It records `hosted_url_path`, `expires_at`, `revoked_at`, `viewed_at`, `view_count`, and `access_result_counts`.
- Allowed access results are `allowed`, `expired`, `revoked`, `not_found`, `auth_required`, and `redaction_blocked`.

GitHub surfaces:

- `pr_comment_markdown` and `github_check_run` reference the same `source_snapshot_id`, `release_id`, `head_sha`, and `audit_bundle_id`.
- A PR comment must include an update marker, gate decision, report link or local artifact path, and bundle verification hint.
- A GitHub check must include conclusion, status, details URL, annotation path, and merge-blocking state.

Audit and replay:

- `audit_bundle_index` links to generated artifact hashes, governance records, chain-of-custody events, retention metadata, and root hash.
- `replay_pack` links failed cases to A1 trace/tool-call evidence, A2 judge evidence, media metadata, and reviewer next actions.

Reviewer and usage:

- `reviewer_board` records reviewer lanes, required approvers, missing evidence counts, waiver state, approval readiness, and per-case review items.
- `usage_ledger` records usage events for imported runs, cases, trace events, grades, report snapshots, export artifacts, hosted views, replay packs, verifier runs, retained bundle bytes, and reviewer board items.

## 7. Safety Contract

ANCHOR: SAFETY_CONTRACT

The manifest and every artifact it references must be safe for customer-facing evidence review.

Required safety fields:

- `contains_secret_values`
- `local_absolute_paths_allowed`
- `raw_signed_urls_allowed`
- `raw_cookies_allowed`
- `raw_tokens_allowed`
- `csv_formula_injection_allowed`
- `redaction_policy_version`
- `redaction_scan_ids`
- `redaction_findings_count`

Safety invariants:

- `contains_secret_values` must be `false`.
- `local_absolute_paths_allowed` must be `false`.
- `raw_signed_urls_allowed` must be `false`.
- `raw_cookies_allowed` must be `false`.
- `raw_tokens_allowed` must be `false`.
- `csv_formula_injection_allowed` must be `false`.
- Any high-confidence redaction finding moves the affected artifact to `redaction_blocked`.
- Workspace paths must be relative paths or explicit redacted placeholders.
- The manifest may print ids, hashes, counts, schema versions, timestamps, status values, and safe error classes only.

## 8. SQL And Audit Linkage

ANCHOR: SQL_AUDIT_LINKAGE

Future SQL-backed Report Center implementations should map the manifest to these tables without changing the artifact ids:

- `shareable_reports`
- `report_exports`
- `report_share_links`
- `report_share_revocations`
- `report_share_views`
- `audit_events`
- `usage_ledger`
- `redaction_scans`

Required audit event families:

- `report.snapshot_created`
- `report.export_queued`
- `report.export_completed`
- `report.export_failed`
- `report.redaction_blocked`
- `report.share_link_created`
- `report.share_link_viewed`
- `report.share_link_revoked`
- `report.bundle_verified`
- `replay_pack.generated`
- `reviewer_board.generated`
- `usage.recorded`
- `retention.purge_planned`

The usage ledger is append-only. Corrections are represented as compensating entries or `usage.adjustment_planned` events, not destructive edits.

## 9. Example Skeleton

ANCHOR: EXAMPLE_SKELETON

```json
{
  "schema_version": "a3.report_center_manifest.v1",
  "manifest_id": "rcm_local_demo_11926",
  "release_id": "local-mock-commercial-gate",
  "run_id": "11926",
  "head_sha": "local-demo-head-sha",
  "source_snapshot_id": "report_snapshot_11926",
  "redaction_policy_version": "a3.export_redaction.v1",
  "artifacts": [
    {
      "artifact_id": "json_report",
      "artifact_name": "JSON report",
      "artifact_kind": "export",
      "schema_version": "a3.export_report.v1",
      "content_type": "application/json",
      "format": "JSON",
      "producer": "report_builder",
      "source_snapshot_id": "report_snapshot_11926",
      "content_hash": "pending",
      "byte_size": "pending",
      "workspace_path": "fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json",
      "redaction_status": "passed",
      "verification_status": "pending",
      "lifecycle_state": "generated",
      "created_at": "2026-07-07T00:00:00.000Z",
      "updated_at": "2026-07-07T00:00:00.000Z",
      "created_by": "a3-local-gate-cli",
      "published_at": null,
      "expires_at": null,
      "revoked_at": null,
      "viewed_at": null,
      "verified_at": null,
      "purged_at": null,
      "retention_policy": "local_demo",
      "blocking_reason": null,
      "audit_event_ids": ["audit_event_json_report_generated"],
      "usage_event_ids": ["usage_event_export_json"]
    }
  ],
  "safety": {
    "contains_secret_values": false,
    "local_absolute_paths_allowed": false,
    "raw_signed_urls_allowed": false,
    "raw_cookies_allowed": false,
    "raw_tokens_allowed": false,
    "csv_formula_injection_allowed": false,
    "redaction_policy_version": "a3.export_redaction.v1",
    "redaction_scan_ids": ["scan_report_center_manifest"],
    "redaction_findings_count": 0
  }
}
```

## 10. Acceptance Guard

ANCHOR: ACCEPTANCE_GUARD

Focused guard:

```text
node --test tests/a3/report_center_manifest_contract.test.mjs
```

This guard should fail if the artifact ids, lifecycle fields, safety fields, or critical schema anchors are renamed without a deliberate contract update.
