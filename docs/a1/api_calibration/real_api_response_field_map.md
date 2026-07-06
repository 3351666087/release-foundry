# Ashr Real API Response Field Map

| Field | Value |
| --- | --- |
| Schema | `ashr.clone.response_field_map.v1` |
| Source label | `a1-real-api-2026-07-07-round9-quota-gate-parity` |
| Source records | `326` |
| Field map version | `a1-api-calibration-2026-07-04` |

## Function Coverage

| Function | Records | Statuses | Response keys | Error keys | Top count keys | Quota blocks |
| --- | ---: | --- | --- | --- | --- | ---: |
| `create_request` | 33 | `error`: 13, `ok`: 2, `planned`: 18 | `_user`, `plan`, `request`, `status` | `error_kind`, `message`, `response`, `response_headers`, `status_code` | - | 11 |
| `create_run` | 2 | `ok`: 1, `planned`: 1 | `_user`, `plan`, `run`, `status` | - | - | 0 |
| `get_dataset` | 8 | `error`: 6, `ok`: 2 | `_user`, `dataset`, `status` | `error_kind`, `message`, `response`, `response_headers`, `status_code` | - | 0 |
| `get_request` | 11 | `error`: 5, `ok`: 6 | `_user`, `request`, `status` | `error_kind`, `failure_summary`, `message`, `response`, `response_headers`, `status_code` | - | 0 |
| `get_run` | 4 | `ok`: 2, `planned`: 1, `timeout`: 1 | `_user`, `plan`, `run`, `status` | `message`, `status_code` | - | 0 |
| `init` | 29 | `ok`: 24, `planned`: 5 | `features`, `notes`, `plan`, `status`, `tenant`, `user` | - | - | 0 |
| `keep_alive` | 27 | `ok`: 23, `planned`: 4 | `db`, `message`, `plan`, `status` | - | - | 0 |
| `list_agents` | 27 | `ok`: 23, `planned`: 4 | `_user`, `agents`, `plan`, `status` | - | `agents` | 0 |
| `list_datasets` | 33 | `ok`: 28, `planned`: 5 | `_user`, `datasets`, `next_cursor`, `plan`, `status` | - | `datasets` | 0 |
| `list_requests` | 34 | `ok`: 31, `planned`: 3 | `_user`, `next_cursor`, `plan`, `requests`, `status` | - | `requests` | 0 |
| `list_runs` | 4 | `ok`: 3, `planned`: 1 | `_user`, `plan`, `runs`, `status` | - | `runs` | 0 |
| `plan_batch` | 2 | `blocked`: 1, `planned`: 1 | `plan` | - | - | 0 |
| `poll_request` | 1 | `planned`: 1 | `plan` | - | - | 0 |
| `poll_run` | 2 | `planned`: 2 | `plan` | - | - | 0 |
| `unknown` | 109 | `completed`: 13, `failed`: 1, `ok`: 33, `partial`: 11, `passed`: 11, `planned`: 7 | - | - | - | 30 |

## Commercial Readiness Notes

- Public report intentionally lists field names, statuses, and quota-block presence only; exact hosted quota counts and raw payloads remain in ignored private evidence.
- Functions with quota blocks need quota-reset or plan-upgrade confirmation before paid mutating probes are scaled.
- Functions with both ok and error statuses are candidates for typed error taxonomy and replay fixture hardening.
