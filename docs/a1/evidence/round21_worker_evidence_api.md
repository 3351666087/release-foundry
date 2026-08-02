# Round21 Worker Evidence API

Worker: A1 Worker-Evidence-API
Date: 2026-07-09

## Scope

This note records public-safe A1 evidence for the Ubuntu-24.04-ReleaseFoundry WSL install, Bash verification, one official ReleaseFoundry API read-only small-batch calibration, and next code tasks for official API parity.

Boundaries:
- Owned public write scope was `docs/a1` only.
- Private live API evidence was written only under ignored `docs/evidence/private_refs/`.
- No desktop key file was read. Authentication material was env-only.
- No raw official API payloads, bearer tokens, API keys, private IDs, or A3 private evidence contents are included here.

## Ubuntu-24.04-ReleaseFoundry / Bash Verification

Commands run from `C:\Users\33516\Documents\ReleaseFoundry`:

```powershell
Test-Path -LiteralPath 'D:\WSL\Ubuntu-24.04-ReleaseFoundry'
Get-Item -LiteralPath 'D:\WSL\Ubuntu-24.04-ReleaseFoundry'
wsl.exe --list --verbose
wsl.exe -d Ubuntu-24.04-ReleaseFoundry -- bash -lc 'echo shell=$SHELL; bash --version | sed -n "1p"; uname -srm; pwd'
```

Public-safe results:
- Install directory exists: `D:\WSL\Ubuntu-24.04-ReleaseFoundry`.
- Directory metadata observed: mode `d-----`, last write time `2026-07-09 13:35:29` local time.
- `wsl.exe --list --verbose` reported `Ubuntu-24.04-ReleaseFoundry` as a WSL2 distro. It was initially stopped, then launched for verification.
- Bash verification succeeded inside the distro:
  - `shell=/bin/bash`
  - `GNU bash, version 5.2.21(1)-release (x86_64-pc-linux-gnu)`
  - `Linux 6.18.33.2-microsoft-standard-WSL2 x86_64`
  - Working directory from the WSL command: `/mnt/c/Users/33516/Documents/ReleaseFoundry`

## Official ReleaseFoundry API Read-Only Calibration

Environment/auth policy:
- `RELEASEFOUNDRY_API_KEY` was present in the environment.
- `RELEASEFOUNDRY_API_KEY` and `RELEASEFOUNDRY_BASE_URL` were not present.
- No key value was printed, copied, or read from disk.

Command:

```powershell
python -B -m packages.sdk.releasefoundry.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json
```

Result summary:
- Status: `ok`
- Total steps: `5`
- Read steps: `5`
- Mutating steps: `0`
- Error steps: `0`
- Quota blocks: `0`
- Estimated calls: `7`
- Modalities: `[]`

Public-safe step/key summary:

| Step | Function | Kind | Status | HTTP status | Response status | Response keys |
| --- | --- | --- | --- | --- | --- | --- |
| `init` | `init` | read | ok | 200 | ok | `features`, `notes`, `status`, `tenant`, `user` |
| `health-check` | `keep_alive` | read | ok | 200 | ok | `db`, `message`, `status` |
| `list-agents` | `list_agents` | read | ok | 200 | ok | `_user`, `agents`, `status` |
| `list-datasets` | `list_datasets` | read | ok | 200 | ok | `_user`, `datasets`, `next_cursor`, `status` |
| `list-requests` | `list_requests` | read | ok | 200 | ok | `_user`, `next_cursor`, `requests`, `status` |

Private evidence path summary:
- Manifest: `docs/evidence/private_refs/a1_worker_evidence_api_readonly_20260709_133939.json`
- Manifest size observed: 5,547 bytes.
- Per-step private records referenced by the manifest remain under ignored `docs/evidence/private_refs/`.
- Public docs include only statuses, counts, command shape, and response key names.

## Readiness Packet Inspection

Inspected public readiness packet: `docs/a1/api_calibration/official_api_readiness_packet.json`.

Current readiness gaps from the packet:
- High: `mutating_create_request_quota_gate` - `create_request` remains blocked until a fresh quota/reset-reviewed plan-batch gate approves the tiny text mutation.
- Medium: `media_modalities_unproven` - image, audio, file, and video envelopes are planned but should wait for reviewed text mutation evidence before paid media probes.
- Medium: `hosted_surface_not_commercially_complete` - official API calibration still does not prove API-key lifecycle, usage ledger, trace ingestion, artifact upload, release evidence, or webhook parity.

Inspected public field parity plan: `docs/a1/api_calibration/official_api_field_parity_plan.json`.

Plan surface:
- Read steps: `init`, `health-check`, `list-agents`, `list-datasets`, `list-requests`.
- Mutating steps: `create-request-text`, then one modality at a time for `image`, `audio`, `file`, and `video`.
- Plan summary estimates 10 total steps, 5 read steps, 5 mutating steps, 17 small-batch calls, and modalities `audio`, `file`, `image`, `text`, `video`.

## Proposed Next Code Tasks For Official API Parity

1. Add a public-safe calibration summary builder that consumes private manifests and emits only status counts, response key sets, quota/error counters, and private path references. This would make this note reproducible without hand extraction.
2. Add a non-mutating official API usage/quota/error-shape probe when the hosted API exposes a read endpoint, keeping output private and summary-only public.
3. Add a quota-gate freshness verifier for `create-request-text` that records reset/review state without exposing raw quota values, then wire it into the mutating calibration acceptance checks.
4. Add a tiny text mutation readiness test path that requires `--include-mutating`, explicit `--modality text`, zero retries, private output, and a fresh quota-gate record before any hosted mutation can run.
5. After text mutation evidence is reviewed, add one-modality-at-a-time media calibration tasks for image, audio, file, and video, each requiring `--allow-paid-media` and a private evidence sink.
6. Add local parity stubs and tests for official hosted surfaces not yet commercially proven: API-key lifecycle, usage ledger, trace ingestion, artifact manifests/uploads, release evidence, and webhooks.
7. Add a public-safety regression test that scans generated A1 public docs for raw payload markers, auth headers, key-looking strings, and private evidence JSON bodies while allowing private path names.

