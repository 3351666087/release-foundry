# Round 53 Official API And Frontend Calibration

Date: 2026-07-11

## Boundary

- The API credential was read only from `RELEASEFOUNDRY_API_KEY` in the process environment.
- No credential value, request payload, raw response, or exact quota count is stored in this public evidence.
- Full records are under the git-ignored `docs/evidence/private_refs/` directory.
- Every mutating attempt used `--max-retries 0`.

## Dry-Run Plan

The read-only plan contained five steps and seven estimated calls:

1. `init`
2. `keep_alive`
3. `list_agents`
4. `list_datasets`
5. `list_requests`

The mutating plans were bounded separately:

- text: one mutating step after the five read-only steps, nine estimated calls total;
- image/audio/file/video: four mutating steps after the five read-only steps, fifteen estimated calls total.

Commands:

```powershell
python -B -m packages.sdk.releasefoundry.calibrate --small-batch --max-retries 0 --limit 8 --output docs/evidence/private_refs/a1_readonly_api_round53_dry_run_20260711.json
python -B -m packages.sdk.releasefoundry.calibrate --small-batch --max-retries 0 --include-mutating --modality text --output docs/evidence/private_refs/a1_round53_text_mutating_dry_run_20260711.json
python -B -m packages.sdk.releasefoundry.calibrate --small-batch --max-retries 0 --include-mutating --allow-paid-media --modality image,audio,file,video --output docs/evidence/private_refs/a1_round53_paid_media_mutating_dry_run_20260711.json
```

## Real Read-Only Batch

Command:

```powershell
python -B -m packages.sdk.releasefoundry.calibrate --execute --small-batch --max-retries 0 --limit 8 --output docs/evidence/private_refs/a1_readonly_api_round53_20260711.json
```

Result:

- manifest status: `ok`;
- five of five steps: `ok`;
- transport status: HTTP 200 for every step;
- error steps: zero;
- quota blocks: zero;
- response key counts were recorded privately, while only field counts and names enter public summaries.

Public summary:

- `docs/a1/evidence/official_api_round53_readonly_public_summary.json`

## Mutating Small Batch

A fresh local `plan-batch` gate returned `wait` because official responses did
not expose quota or reset headers. This is missing quota evidence, not evidence
that capacity was available. The user had explicitly authorized real paid API
calibration, so the supported audited override path was used for one text
request before considering media scale-up.

Command shape:

```powershell
python -B -m packages.sdk.releasefoundry.calibrate --execute --small-batch --max-retries 0 --include-mutating --modality text --allow-quota-override --quota-override-reason <public-safe-audit-reason> --output docs/evidence/private_refs/a1_round53_text_mutating_real_20260711.json
```

Result:

- five read-only steps remained `ok` with HTTP 200;
- the text `create_request` reached the official API once;
- the transport envelope was HTTP 200, but the API result was an error;
- the safe classifier marked one quota block;
- no retry occurred;
- image, audio, file, and video mutations were not submitted after the text
  control failed, preventing purposeless repeated calls under unchanged quota
  evidence;
- no charge or generation success is claimed because no billing receipt or
  completed request was observed.

Public summary:

- `docs/a1/evidence/official_api_round53_text_mutating_public_summary.json`

## Frontend Mirror Calibration

The in-app Browser controller and the Chrome controller were both attempted
before the static fallback. Each failed during local control-runtime asset
initialization, before an ReleaseFoundry page could be navigated or inspected. The Chrome
retry occurred after the user opened Chrome, but the local Node control runtime
still reported a missing Windows kernel-asset path. No credential was entered,
no live dashboard screenshot was captured, and no live UI field or workflow
claim is made for this round.

Following the agreed fallback order, calibration continued against the
user-provided frontend mirror. The mirror is static evidence only; it does not
replace a successful official-page or authenticated-dashboard observation.

The mirror archive contained 589 entries. Read-only term extraction found:

- the hosted lab bundle contains `refresh_token` and `session_id` strings;
- official Python and TypeScript VM integration/API reference pages expose
  `session_id`;
- observability and request UI bundles also reference session identifiers.

These observations do not prove an official account-session rotation API.
VM/voice/observability session identifiers and hosted authentication internals
may have different semantics. Round 53's refresh rotation and reuse-detection
contract is therefore documented as an ReleaseFoundry commercial security boundary,
not as a claimed official ReleaseFoundry field match.

Source:

- `ReleaseFoundry_frontend_mirror_20260707_125507.zip` (user-provided local archive;
  the absolute host path is intentionally omitted)

## Peer Impact

- A2 `58fe8762` adds a public multimodal real-API smoke schema and evidence.
  A1 already keeps text, image, audio, file, and video as first-class request
  modalities; no A2 judge semantic was changed here.
- A3 `978a1cb2` adds an A1/A2 contract radar. It consumes public A1 evidence
  and route/capability artifacts; Round 53 must keep those artifacts public-safe
  and versioned, but no A3 dashboard file is modified by A1.

## Code Tasks

1. Keep quota decisions distinct from HTTP transport status in Python and TS.
2. Preserve the five-modality envelope even when mutating capacity is blocked.
3. Publish session lifecycle as a versioned local security contract, without
   presenting frontend string matches as official API parity.
4. Require a changed quota/usage signal before the next paid media batch.
5. Keep private response records ignored and expose only redacted summaries.
