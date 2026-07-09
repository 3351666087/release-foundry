# Round20 Frontend Dashboard DTO Evidence (A1)

Date: 2026-07-08
Worker: A1 Round20 official API + frontend DTO evidence

## Scope

This round turns the Round19 frontend mirror extraction into public DTO fixtures for the usage/quota/API-key dashboard response shapes. The fixture is synthetic and public-safe: it uses frontend mirror field names, labels, threshold expectations, and redaction notes only.

Inputs inspected:
- `docs/a1/evidence/round19_frontend_api_usage_quota_lifecycle.md`
- `tests/a1/fixtures/round19_frontend_contract_public.json`
- `docs/evidence/private_refs` filenames and summary/index-style artifacts for quota-stop/no-quota context only

Raw private API payloads, auth values, cookies, browser storage, account identifiers, and response bodies were not copied or summarized here.

## Public DTO Fixture

Created:
- `tests/a1/fixtures/round20_frontend_dashboard_dtos_public.json`

The fixture covers these public dashboard response shapes:
- `get_usage`
- `list_api_keys`
- `billing_get_status`

The usage shape keeps the frontend mirror metric keys and buyer-facing labels:
- `videos` -> `Videos`
- `images` -> `Images`
- `simulations` -> `Simulations`
- `audios` -> `Audio`
- `files` -> `Files`
- `graded_scenarios` -> `Graded scenarios`
- `observations` -> `Observations`
- `voice_minutes` -> `Voice minutes`

Quota cards model the Round19 thresholds:
- below 75 percent: `normal`
- 75 through 90 percent: `warning`
- above 90 percent: `error`
- hard cap at/above limit: `Limit reached`
- overage cap above included usage: `Overage billing`
- overage under absolute limit: `Over included usage`

API-key cards include frontend mirror fields such as `api_key_id`, `created_at`, and `expires_seconds`, while explicitly representing one-time secret state as already hidden.

## Tests

Created:
- `tests/a1/test_frontend_dashboard_dtos.py`

Assertions cover:
- Round20 DTO functions remain `get_usage`, `list_api_keys`, and `billing_get_status`.
- Round20 usage labels match the Round19 frontend contract fixture.
- API-key DTOs retain frontend mirror field names and the Round19 empty state.
- Quota cards cover normal, warning, error, hard-limit, overage, and over-included states.
- Public fixture keys and serialized content avoid secret/token/private-payload fields.

## API Probe

No live official API probe was run in this round. The existing private_refs quota/noquota artifacts were treated as private evidence context only, and this public fixture remains synthetic.
