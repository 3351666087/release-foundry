# P3 Official Parity Roadmap And Media Evidence Queue

## Goal

Turn the clean-room official Ashr frontend mirror and media calibration evidence into an actionable A3 dashboard workflow.

This pass does not copy official source code, styles, assets, cookies, tokens, account data, or signed media URL values. It uses only A3-owned code and redacted fixtures.

## Added Capability

- `summarizeOfficialParityRoadmap()` now has a visible dashboard panel.
- `media_readiness.evidence_queue` is visible in the Media Readiness panel.
- JSON export includes `official_parity_roadmap`.
- Markdown export includes `Official Parity Roadmap`.
- Print/PDF report preview includes `Official Parity Roadmap`.
- Report Center copy now names the official parity roadmap as part of the release evidence packet.

## What The Roadmap Explains

- Which official Ashr pages A3 should copy now.
- Which official Ashr pages are partial or future work.
- Which official Ashr pages should stay out of scope for the student MVP.
- Why login, API-key creation, team invites, billing checkout, and destructive cloud mutations should remain disabled.
- Which media channels still need redacted signed URL calibration before live preview rendering.

## Media Evidence Queue

The queue ranks media cases for review without rendering live signed URLs. Each row shows:

- case id
- primary media type
- media channels
- evidence item count
- VM stream count
- preview policy
- next action

The current policy stays metadata-only until audio/image/video signed URL expiry and redaction behavior are confirmed with safe samples.

## Verification

Focused tests:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Expected result for this pass:

```text
76 tests pass, 0 fail
```

Screenshots:

- `docs/screenshots/a3-dashboard-official-parity-media-queue.png`
- `docs/screenshots/a3-dashboard-media-evidence-queue.png`
- `docs/screenshots/a3-dashboard-media-evidence-queue-detail.png`

## Safety

- No `.env.local` change.
- No API key, token, cookie, email, account id, raw signed URL, or official source file is committed.
- A3 remains local/read-only for cloud/admin concepts.

## Next Growth Targets

- Add screenshot evidence for the new roadmap panel.
- Add live GitHub check-run wiring for the existing dry-run PR gate adapter.
- Add incident replay UI lanes for highest-risk failed cases.
- Add redacted image/audio/video media samples when safe evidence is available.
- Add enterprise self-host configuration shell without real cloud mutation.
