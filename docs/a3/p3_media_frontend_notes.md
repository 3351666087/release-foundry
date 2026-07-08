# P3 Media Frontend Notes

## Purpose

This note records the current official Ashr frontend evidence that matters for A3 media and usage/quota work.

## Confirmed Frontend Logic

Authenticated Chrome/CDP observation on 2026-07-06 confirmed these top-level pages:

| Page | Path | Confirmed modules | Frontend API functions |
|---|---|---|---|
| Usage | `/?tab=usage` | Images, Audio, Files, Upgrade | `get_usage`, `billing_get_status` |
| Datasets | `/?tab=analysis` | New dataset, Type, Agent, Creator, Status, Runs, Sort, Group | `list_datasets`, `list_requests`, `list_folder_memberships` |
| Analytics | `/?tab=analytics` | Agents, Datasets, Graded runs, Overall pass rate, Run volume, Pass rate over time, Runs by agent, Pass rate by agent | `list_agents`, `list_datasets` |
| Trust | `/?tab=trust` | Public trust page, Preview, Refresh | `get_trust_certificate_status`, `preview_trust_certificate` |

No headers, cookies, browser token values, response bodies, account values, or screenshots were saved.

## Usage / Quota Finding

The frontend visibly exposes media quota channels:

- Images
- Audio
- Files

The Usage page showed 0 usage for the observed account and limits of 100 Images, 200 Audio, and 100 Files.

The frontend functions `get_usage` and `billing_get_status` were discovered from request bodies, but direct API-key calls to those functions returned 403 with OAuth-only messages. This means A3 should treat usage/quota as frontend-confirmed and API-key-gated for now.

Evidence:

- `fixtures/a3/p3/ashr_frontend_usage_workflow.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`

## Media Signed URL Finding

The read-only media API calibration reconfirmed:

- `signed_url` exists for file-like dataset actions.
- audio/image/video signed URL behavior is still unconfirmed.
- `output_path` appears for media actions.
- media capability flags appear in request shapes.

Evidence:

- `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`
- `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`
- `docs/a3/p3_signed_media_url_coverage.md`

## A3 MVP Decision

A3 should copy:

- media quota awareness in the Product Console
- Images/Audio/Files channels as read-only evidence
- explicit API-key/OAuth gap wording
- no live signed URL rendering

A3 should not copy yet:

- billing/upgrade mutation flows
- live media signed URL rendering
- public trust publishing
- account/team/API-key management

## 2026-07-06 A3 Implementation Update

A3 now includes a product-level `Media Readiness` panel and report section.

It shows:

- media case count
- media evidence item count
- VM stream count
- observed media channels
- output path coverage
- signed URL key coverage
- confirmed signed URL types
- unconfirmed signed URL types
- live-rendering policy

A3 also includes a read-only `Cloud Console Shell` panel that mimics official cloud/admin surfaces without enabling real login, API-key, team, billing, trust-publishing, or cloud mutation flows.

## Remaining Gap

A3 still needs one UI-visible populated hosted run to observe real frontend run detail, case detail, trace/timeline, expected-vs-actual, tool calls, and media preview behavior.
