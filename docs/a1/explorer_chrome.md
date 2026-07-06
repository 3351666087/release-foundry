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
- Developer plan: `$39 /mo`, hard cap, 5,000 graded scenarios/mo, 250,000 observations/mo, 1,000 voice minutes/mo, 14 day retention, 1 project.
- Startup plan: `$500 /mo`, metered overage, 100,000 graded scenarios/mo, 10,000,000 observations/mo, 50,000 voice minutes/mo, 90 day retention, unlimited projects.
- Annual toggle was publicly visible. Developer annual price: `$390 /yr`; Startup annual price: `$5,000 /yr`; Enterprise remains custom/contact sales.
- Enterprise plan: custom/contact sales for graded scenarios, observations, voice minutes, retention, and projects.

## Dashboard Shell

- Earlier read-only checks reached title `Ashr Labs`, URL `https://lab.ashr.io/?tab=analysis`, sign-in actions `Continue with Google` and `Continue with Microsoft`, Terms/Privacy links, public ashr.io/Docs/Blog links, onboarding text `Create your workspace`, and a `Pick a plan` panel.
- Earlier unauthenticated onboarding plan copy included `FREE $0/mo`, `100 images / mo`, `200 audio files / mo`, `100 sample files / mo`, and `CUSTOM Let's talk` with unlimited images/audio/sample files.
- Round 4 could not reproduce the exact sign-in/onboarding plan-copy state; it reached title `Ashr Labs`, public Home/Docs/Blog links, and a dashboard-like `Datasets`/loading shell at `https://lab.ashr.io/?tab=analysis`.
- Private dashboard data, project data, API key creation, billing portal, checkout, and server-side grading state were not verified.

## API And VM Boundary Notes

- Python API reference publicly lists `list_api_keys(include_inactive=False)` and `revoke_api_key(api_key_id)`.
- TypeScript API reference publicly lists `listApiKeys(includeInactive?)` and `revokeApiKey(apiKeyId)`.
- VM docs show `test.set_vm_stream(provider, session_id=None, duration_ms=None, logs=None, metadata=None)`.
- VM log entry fields are `ts`, `type`, and `data`; docs state VM logs are not auto-captured.

## Round 4 Recheck

- `https://ashr.io/` remained accessible with title `Ashr`, headline `Evals for Agents That Actually Work`, and public nav links to Docs, Plans, Blog, Book a Call, and Login.
- Monthly and annual public plan copy remained visible: Developer `$39 /mo` and `$390 /yr`; Startup `$500 /mo` and `$5,000 /yr`; Enterprise custom/contact sales.
- Python API reference still listed `list_api_keys(include_inactive=False)`, `revoke_api_key(api_key_id)`, `set_vm_stream(...)`, and the observability feature flag note.
- VM integration guide still described VM streams as per-test metadata and showed `set_vm_stream` / VM log fields.
- TypeScript overview still stated Testing Platform and Observability share the SDK/API key while Observability requires a tenant feature flag.
- `https://lab.ashr.io/` reached title `Ashr Labs`, public Home/Docs/Blog links, and a dashboard-like `Datasets`/loading shell at `https://lab.ashr.io/?tab=analysis`; the earlier sign-in/onboarding plan-copy state was not reproduced, and no authenticated dashboard data was used as clone input.

## Round 5 Recheck

- Main-agent read-only Chrome check again found public homepage/docs/API/VM/TypeScript pages accessible and consistent with the field map: homepage title `Ashr`; H1 `Evals for Agents That Actually Work`; public nav Home/Docs/Plans/Blog/Book a Call/Login; Python docs show `pip install ashr-labs`; API reference shows `list_api_keys`, `revoke_api_key`, `set_vm_stream`, and observability feature-flag language.

## 2026-07-04 Logged-In Dashboard Check

- Chrome was already logged in to `lab.ashr.io`.
- Main-agent read-only check navigated only to `https://lab.ashr.io/?tab=analysis`, not to API key pages.
- Page title was `Ashr Labs`; login/sign-in text was not present.
- Dashboard shell hints included `Datasets` and `Runs`.
- Screenshot path: `docs/evidence/private_refs/ashr_lab_analysis_2026-07-04.png` (ignored private evidence, not for commit).
- Public pricing copy remained visible: Developer `$39 /mo`, Startup `$500 /mo`; Explorer-Chrome also verified annual Developer `$390 /yr` and Startup `$5,000 /yr`.
- VM docs still state EvalRunner does not auto-capture VM logs, show `test.set_vm_stream(...)`, and describe VM log fields `ts`, `type`, and `data`.
- Lab shell was variable across read-only checks in the same round. Main-agent Chrome saw title `Ashr Labs` with a `Datasets` loading shell at `https://lab.ashr.io/?tab=analysis`; Explorer-Chrome reproduced the unauthenticated sign-in/onboarding shell with `Continue with Google`, `Continue with Microsoft`, `Create your workspace`, `Pick a plan`, `FREE`, `$0/mo`, and quota copy. No private dashboard data, authenticated state, key creation/enforcement, billing, hosted grading, or observability rendering was verified.

## 2026-07-06 A1 Queue Lease Round Recheck

- Main-agent Chrome check was read-only and did not open API Keys, payment, checkout, or credential pages.
- `https://ashr.io/` loaded with title `Ashr`; public nav still included Docs and Plans. The automatic text extractor found plan tier names `Developer`, `Startup`, and `Enterprise`; detailed price text was not re-extracted in this main-thread pass, while Explorer-Chrome separately observed Developer `$39/mo`, Startup `$500/mo`, and Enterprise custom/contact sales.
- Python API reference remained public and exposed `AshrLabsClient`, `from_env`, `create_request`, `list_requests`, `trace`, `TestBuilder`, and `RunBuilder`.
- TypeScript API reference remained public and exposed `AshrLabsClient`, `fromEnv`, `createRequest`, `listRequests`, `waitForRequest`, `Trace`, and `Generation`.
- `https://lab.ashr.io/?tab=usage` loaded with title `Ashr Labs` and a visible `Usage` signal. The automated extractor did not reliably capture Images/Audio/Files counters in this pass, so no usage counter values are recorded here. API Keys was not opened to avoid key exposure.
