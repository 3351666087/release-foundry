# Explorer Chrome Calibration

Date: 2026-07-03
Mode: read-only Chrome checks. No Ashr API key, password, payment data, or other secret was entered.

## Public Site

- `https://ashr.io/` loaded with title `Ashr`.
- Homepage headline observed: `Evals for Agents That Actually Work`.
- Public nav links observed: Home, Docs, Plans, Blog, Book a Call, Login.
- Login points to `https://lab.ashr.io/`.
- Public setup copy observed: `Set up agent testing in one command.` and `Scale agent testing by usage.`

## Python SDK Docs

- `https://ashr.io/docs/python-sdk/overview/` loaded with title `Ashr Labs Python SDK | Ashr`.
- Public docs show `pip install ashr-labs`.
- Public docs show SDK surfaces used only as field-map calibration: `AshrLabsClient`, `EvalRunner`, `RunBuilder`, `Agent`, `client.trace()`, `Span`, `Generation`, and `observability`.
- Testing docs show the local agent protocol `respond()` / `reset()`, `EvalRunner.from_dataset`, `runner.run(...)`, `runner.run_and_deploy(...)`, `tool_calls`, `arguments`, `arguments_json`, `max_workers`, and dashboard deeplinks.
- VM integration docs show `set_vm_stream`, provider/session/log metadata, browser-agent logs, and the note that VM streams are not auto-captured.
- API reference shows API-key authentication, `ASHR_LABS_API_KEY`, default base URL `https://api.ashr.io/testing-platform-api`, dataset/run methods, observability trace/span/generation methods, and feature-gated observability behavior.

## TypeScript SDK Docs

- `https://ashr.io/docs/typescript-sdk/overview/` loaded with title `Ashr Labs TypeScript SDK | Ashr`.
- Public TypeScript docs expose parallel Testing Platform and Observability sections.
- TypeScript overview states Observability is a separate product and requires the tenant observability feature flag.
- TypeScript docs are recorded for product calibration only; A1 implemented Python local clone surfaces in this round.

## Public Plans And Usage

- Plans section loaded from `https://ashr.io/#plans`.
- Billing toggle copy observed: `Monthly` and `Annual Save 17%`.
- Developer plan: `$39/mo`, hard cap, 5,000 graded scenarios/mo, 250,000 observations/mo, 1,000 voice minutes/mo, 14 day retention, 1 project.
- Startup plan: `$500/mo`, metered overage, 100,000 graded scenarios/mo, 10,000,000 observations/mo, 50,000 voice minutes/mo, 90 day retention, unlimited projects.
- Annual toggle was publicly visible. Developer annual price: `$390/yr`; Startup annual price: `$5,000/yr`; Enterprise remains custom/contact sales.
- Enterprise plan: custom/contact sales for graded scenarios, observations, voice minutes, retention, and projects.

## Dashboard Shell

- `https://lab.ashr.io/` reached title `Ashr Labs` and URL `https://lab.ashr.io/?tab=analysis`.
- Current unauthenticated shell shows sign-in actions `Continue with Google` and `Continue with Microsoft`, Terms/Privacy links, public ashr.io/Docs/Blog links, onboarding text `Create your workspace`, and a `Pick a plan` panel.
- Unauthenticated onboarding plan copy observed: `FREE $0/mo`, `100 images / mo`, `200 audio files / mo`, `100 sample files / mo`, and `CUSTOM Let's talk` with unlimited images/audio/sample files.
- Only unauthenticated shell/onboarding state and public nav links were checked. Private dashboard data, project data, API key creation, billing portal, checkout, and server-side grading state were not verified.

## API And VM Boundary Notes

- Python API reference publicly lists `list_api_keys(include_inactive=False)` and `revoke_api_key(api_key_id)`.
- TypeScript API reference publicly lists `listApiKeys(includeInactive?)` and `revokeApiKey(apiKeyId)`.
- VM docs show `test.set_vm_stream(provider, session_id=None, duration_ms=None, logs=None, metadata=None)`.
- VM log entry fields are `ts`, `type`, and `data`; docs state VM logs are not auto-captured.
