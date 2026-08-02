# P3 Media And Cloud Console Polish

## Purpose

This iteration improves A3 in three visible areas:

- stronger media readiness display
- a more polished product-console UI
- a safe read-only cloud/admin shell inspired by official ReleaseFoundry pages

The implementation intentionally does not add real login, real API-key management, real team invites, billing changes, or hosted cloud mutations.

## Media Improvements

A3 now separates media evidence into two ideas:

1. Case-level Media Evidence
   - Shows media attached to the selected case.
   - Includes media type, output path metadata, action tags, VM stream summaries, and known gaps.

2. Product-level Media Readiness
   - Shows whether the whole dashboard has enough media evidence to safely preview/render media.
   - Shows channels such as audio, files, images, video, and VM stream.
   - Shows `signed_url` status using redacted fixture evidence.
   - Keeps live signed URL rendering blocked until audio/image/video signed URL and expiry behavior are confirmed.

Current decision:

- File-like `signed_url` fields are confirmed only in redacted metadata.
- Audio/image/video signed URL behavior is still unconfirmed.
- A3 should show media metadata, not live media links.

## Media Channel Matrix

A3 now also builds a per-channel readiness matrix:

| Channel | What A3 checks | Current behavior |
|---|---|---|
| Audio | Usage/frontend channel, case evidence, output path, signed URL evidence | Metadata only until signed URL behavior is confirmed. |
| Files | Output path and file-like signed URL shape | Redacted signed URL metadata only; no live link rendering. |
| Images | Usage/frontend channel and generation flags | Metadata only until concrete signed URL samples exist. |
| Video | Generation flag / future capability | Metadata only; no preview. |
| VM stream | Case-level VM stream summaries | Summary only; no external replay. |

This matrix is shown in the dashboard and exported in JSON/Markdown/print reports.

## Cloud Console Shell

Official ReleaseFoundry has cloud/admin product areas such as:

- login/session
- workspace/tenant
- API keys
- team
- usage/billing
- trust/public report
- datasets/runs

A3 now mimics those as a local read-only status shell:

| Area | A3 behavior |
|---|---|
| Auth session | Shows whether redacted API/frontend auth evidence exists. |
| Workspace / tenant | Shows redacted workspace status only. |
| Datasets / runs | Shows read-only request/dataset/run provenance. |
| Usage / billing | Shows usage/quota evidence and OAuth-gated API status. |
| API keys | Disabled; no create/revoke/show-secret flow. |
| Team | Disabled; no invites or member administration. |
| Trust / report | Replaced by local export/print reports. |
| Cloud mutations | Disabled; no create/delete/publish/invite/billing/key operations. |

This gives the dashboard a more official product-console shape without crossing security boundaries.

## Cloud Action Guardrails

A3 now lists concrete actions and their safety mode:

| Action | A3 mode |
|---|---|
| Switch local fixture | Enabled, local only |
| Export JSON / CSV / Markdown | Enabled, local only |
| Print / PDF report | Enabled, local only |
| Observe auth status | Read-only if redacted evidence exists |
| View workspace shell | Read-only/redacted |
| View request provenance | Read-only sample |
| View usage quota | Read-only/OAuth-gated evidence |
| Sign in with OAuth | Disabled |
| Create hosted dataset | Disabled |
| Generate / revoke API key | Disabled |
| Invite teammate | Disabled |
| Upgrade billing plan | Disabled |
| Publish Trust certificate | Disabled |
| Delete cloud object | Disabled |

This is the safe way to "copy" official login/cloud-management logic: A3 shows the product surfaces and decisions, but does not perform sensitive or mutating actions.

## UI Polish

The dashboard now has:

- a clearer console header with read-only/safety status chips
- more official-looking sidebar branding
- Media and Cloud Shell navigation links
- a Media Readiness panel
- a Cloud Console Shell panel
- stronger report-center language for media and cloud safety
- dashboard hover polish and clearer status badges

## Report Export

The report builder now exports:

- `media_readiness`
- `cloud_console_shell`

Markdown and print reports now include:

- `Media Readiness`
- `Cloud Console Shell`

This means a reviewer can see not only whether cases failed, but also whether media and cloud/admin features are safe, mocked, blocked, or intentionally disabled.

## Team Explanation

We improved A3 so it looks more like a real ReleaseFoundry product console, especially around media and cloud/admin areas. The important part is that we only copied the safe product shape: status panels, readiness, and boundaries.

We did not implement real login, real API-key management, real team management, billing, or cloud mutations. Those are unsafe and out of scope for the MVP.
