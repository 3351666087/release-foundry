# P3 Signed Media URL Coverage

## Purpose

This note records what A3 can safely claim about real Ashr signed media URL fields. It only uses redacted local fixtures and does not store live signed URL values.

## Evidence

Coverage fixture:

- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`

Input scope:

- 18 redacted P3 fixture files under `fixtures/a3/p3`
- No raw URL values, request headers, cookies, or tokens were saved

## Coverage Summary

| Field / Media evidence | Confirmed coverage |
|---|---:|
| `signed_url` keys | 2 |
| `signed_url` nearest media type: `file` | 2 |
| `signed_url` nearest media type: `audio` | 0 |
| `signed_url` nearest media type: `image` | 0 |
| `signed_url` nearest media type: `video` | 0 |
| `output_path` keys | 122 |
| `output_path` nearest media type: `file` | 8 |
| `output_path` nearest media type: `audio` | 23 |

2026-07-06 refresh:

- New read-only signed-url probe saved `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`.
- The refresh again found 2 `signed_url` paths.
- Both paths are attached to the same file-like dataset action shape.
- No raw signed URL values were saved.

Request configuration evidence also mentions media capabilities:

| Request flag type | Evidence |
|---|---:|
| accepted `audio` input | 18 |
| accepted `file` input | 18 |
| accepted `image` input | 18 |
| accepted `video` input | 1 |
| `generate_audio` | 19 |
| `generate_files` | 19 |
| `generate_images` | 19 |
| `generate_videos` | 2 |

## Interpretation

Current evidence confirms the field name `actions[].signed_url` for file-like dataset actions only.

Current evidence does not confirm direct signed URL behavior for:

- audio
- image
- video

Audio has stronger `output_path` and metadata evidence, but no direct `signed_url` sample in the redacted fixtures. Image and video are visible as accepted/generation options, but not as concrete signed URL samples.

## A3 Decision

A3 should:

- preserve `signed_url` as redacted metadata when it appears
- show media type, action tags, output path presence, audio tags, and VM stream evidence
- continue treating live signed media rendering as blocked

A3 should not:

- render live signed media links
- assume audio/image/video signed URL behavior from file-only evidence
- save raw signed URL values in docs, fixtures, screenshots, or reports

## Next Proof Needed

To enable live rendering later, A3 needs a sanitized sample for each intended media type:

- audio signed URL sample
- image signed URL sample
- video signed URL sample
- explicit expiry/access behavior for signed URLs
- frontend rule for whether links are displayed, proxied, or downloaded
