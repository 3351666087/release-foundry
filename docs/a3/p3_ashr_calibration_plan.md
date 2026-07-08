# P3 Ashr Calibration Plan

## Purpose

P3/G3 calibrates the local Ashr clone against the real Ashr platform. The goal is not a large rewrite. The goal is to learn how real Ashr names and nests the product objects that A3 needs to display:

- agent
- dataset / eval / evaluation
- scenario / test
- run
- trace / observability trace
- tool call
- expected vs actual
- score
- pass/fail
- failure reason / failure class
- dashboard and report fields

The first usable outcome is a small, documented bridge from real Ashr samples into the existing A3 dashboard fixture shape.

## Current local A3 contract

A3 currently reads two local fixture shapes:

- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`

The dashboard/report layer expects:

- run list data from `runs[]`
- case detail data from `runs[].cases[]`
- expected vs actual data from `case.expected` and `case.actual`
- trace timeline data from `case.trace_events[]`, falling back to `case.observations[]`
- grading data from `grade_results[]`
- failure clustering from `primary_failure_class`

The shared normalization code lives in `services/report/report_builder.mjs`.

## Real Ashr evidence sources

Use these sources in order:

1. Local merged clone contracts:
   - `docs/a1/schemas/run_result.schema.json`
   - `docs/a1/schemas/case_result.schema.json`
   - `docs/a1/schemas/trace_event.schema.json`
   - `docs/a1/schemas/observation.schema.json`
   - `docs/a2/a1_a3_handoff.md`
   - `services/judge/schemas.py`
   - `docs/a3/mock_fixture_contract.md`
2. Local PyPI artifact from A1:
   - `docs/a1/_pypi_artifacts/ashr_labs-0.3.1.tar.gz`
   - `docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl`
3. Official Ashr docs:
   - `https://ashr.io/docs/python-sdk/overview`
   - `https://ashr.io/docs/python-sdk/api-reference`
4. Sanitized smoke-test fixtures created during P3:
   - `fixtures/a3/p3/ashr_auth_check.redacted.json`
   - `fixtures/a3/p3/ashr_field_sample.redacted.json`

## Safety rules

- Read keys only from `.env.local` or inherited environment variables.
- Accept either `ASHR_API_KEY` or `ASHR_LABS_API_KEY`, then map to SDK env only inside the current process.
- Never print a key, token, raw Authorization header, account email, or tenant-specific private data.
- Never commit `.env.local`.
- Save only redacted API samples.
- If a subagent is used, it may write code and may call the Ashr API through environment variables, but it must follow the same no-print, no-commit secret rules.
- Do not modify A1 runner core behavior.
- Do not modify A2 judge semantics.
- Do not break the existing A3 mock dashboard.

## Calibration workflow

1. Confirm Git and secret hygiene.
   - Fetch origin when the network allows.
   - Confirm the P3 branch is based on merged `main`.
   - Confirm `.env.local` is ignored.
2. Read local contracts.
   - A1 tells us the run, case, trace, observation, and tool-call shape.
   - A2 tells us the grade, score, pass/fail, and failure-analysis shape.
   - A3 tells us the dashboard view model shape.
3. Read SDK and docs.
   - Confirm `AshrLabsClient`, `RunBuilder`, `TestBuilder`, `Trace`, and list/get methods.
   - Confirm read-only methods for smoke tests.
4. Run a minimal read-only smoke test.
   - Validate authentication with `init()` or `health_check()`.
   - List a small number of agents, datasets, runs, requests, and observability traces if available.
   - Do not create large data.
5. Save sanitized evidence.
   - Redact ids where needed.
   - Replace emails, names, tenant values, keys, URLs, and private text with `[REDACTED]` or stable placeholders.
6. Map fields.
   - Mark each mapping as `verified`, `probable`, or `unknown`.
   - Keep unknown fields visible instead of guessing.
7. Add a small mapper only if the shape is clear.
   - Suggested paths:
     - `services/report/p3_ashr_mapper.mjs`
     - `tests/a3/p3_ashr_mapper.test.mjs`

## Mock-to-real strategy for A3

The A3 dashboard should keep working from mock fixtures. P3 should add a small adapter beside the current report builder:

1. Real Ashr API sample comes in.
2. Mapper extracts runs, tests/cases, action results, expected/actual comparisons, metrics, and failure fields.
3. Mapper emits the same shape A3 already understands:
   - `a3.dashboard_fixture.v1`
   - `a3.grade_fixture.v1`
4. Dashboard keeps loading fixture-shaped JSON.

This avoids rewiring the whole UI while A1/A2/A3 are still learning the real platform.

## Open assumptions

- Real Ashr testing runs are represented by `Run` objects with a nested `result`.
- Server grading appears inside or beside `result.aggregate_metrics`.
- Real test cases are likely represented as `result.tests[]`.
- Expected vs actual appears inside each test's `action_results[]`.
- Observability traces may be separate from testing runs and may use `trace.observations[]`.
- Failure class names may not match A2 taxonomy exactly, so P3 should store raw platform failure fields plus a normalized A2/A3 class.
