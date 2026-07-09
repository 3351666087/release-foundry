# Worker Runtime Queue Retry + Dead Letter Evidence

Date: 2026-07-08

Scope: A1 Ashr++ worker runtime cloud API skeleton and local queue worker. No secrets were read or written.

## Capability

Implemented production-shaped queue retry/dead-letter lifecycle support in the local cloud API runtime:

- Queued runs now carry `attempt`, `max_attempts`, `last_error`, and `dead_letter_reason` fields.
- `mark_run_running` increments `attempt` when a queued/submitted run starts a new execution attempt.
- `fail_run` records `last_error` and clears the active lease.
- `retry_run` requeues failed runs while retry capacity remains.
- `dead_letter_run` moves exhausted failed runs to terminal `dead_lettered` status.
- `CloudQueueWorker.replay_incomplete_runs` can replay failed runs, respects max attempts, and stops exhausted runs in the dead-letter state.
- Worker DB-shaped schema docs now expose retry/lease/dead-letter columns and a lease-expiry index.

## Verification

Commands run from repository root:

```powershell
python -m pytest tests/a1/test_cloud_api.py -q
python -m pytest tests/a1/test_worker_data_model.py tests/a1/test_cloud_api.py -q
```

Observed results:

```text
26 passed in 2.63s
30 passed in 2.75s
```

## Regression Coverage

Added coverage for:

- Service-level retry budget: failed run requeues until `max_attempts`, then becomes `dead_lettered`.
- Worker replay retry budget: failed queued worker run is retried once, fails again, then dead-letters on the next replay scan.
- Existing queue lifecycle, cancellation, lease heartbeat/reclaim, state roundtrip, and fixture tests continue to pass.

## Files Touched

- `services/api/runtime.py`
- `services/api/queue_worker.py`
- `services/api/__init__.py`
- `services/api/data_model.py`
- `tests/a1/test_cloud_api.py`
- `docs/a1/schemas/worker_data_model.schema.json`
- `docs/a1/schemas/worker_data_model.indexes.json`
- `docs/a1/schemas/worker_data_model.migration.sqlish`
- `docs/a1/docs/evidence/worker_runtime_queue_retry_dead_letter_2026_07_08.md`
