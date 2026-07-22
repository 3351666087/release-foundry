# A1/A3 Acceptance Remediation - 2026-07-22

## Scope

This round remediates the deterministic A1/A3 findings in the dual-customer
acceptance report. The work is based on remote `main` at `c30a37e` and keeps
the A2 judge and Decision Ledger semantics unchanged.

## Remediated findings

| Finding | Remediation | Evidence |
| --- | --- | --- |
| F-001 installer secret contract | PowerShell and POSIX installers accept required secrets from either a private env file or the invoking process environment. | `infra/install/install.ps1`, `infra/install/install.sh`, `infra/docker/self-host.env.example` |
| F-002 dashboard gradients | Replaced dashboard gradients with solid/alpha backgrounds so the approved zero-gradient visual contract is deterministic. | `apps/dashboard/src/styles.css` |
| F-003 fail badge color | Aligned the failure background token with the approved `#fff0ee` contract. | `apps/dashboard/src/styles.css` |
| F-004 WSL capability probe | WSL tests now require the configured distribution and a working `/bin/sh` probe, not only the launcher executable. | `tests/a1/test_rust_verifier_sidecar.py` |
| F-005 Rust target path | Rust verification uses `CARGO_TARGET_DIR` when supplied and resolves the expected binary from that directory. | `tests/a1/test_round53_identity_security_integration.py` |
| F-006 tool capability handling | Docker, Go, Node/npm, TypeScript, and Cargo-dependent tests skip explicitly when the required local tool is unavailable. | changed A1 tests and `tests/integration/test_a1_go_server_python_sdk.py` |

## Verification

- A1 and integration suites: `1358 passed, 68 skipped, 0 failed`.
- A3 Node suite: `532 passed, 1 skipped, 0 failed`.
- Webapp `npm run check`: TypeScript check and Next.js static build passed;
  15 pages were generated.
- Full Playwright suite: `48 passed, 0 failed`.
- `git diff --check`: passed.
- `.env.local` is ignored and absent from Git status.

## Environment boundary

Docker Desktop is installed, but the Docker service is stopped and the current
user cannot start it. The Docker client probe through its installed path timed
out, and WSL reports that its required Linux component is unavailable.
Therefore live PostgreSQL migrations, RLS, Compose startup, health checks, and
payment smoke tests remain unqualified. The skipped tests are environment
skips, not claims of runtime success.

## A2 boundary

The GitHub A2 branch remains at `585a9931a652ce0b36a3a7fee006974aa2fe793a` at
the time of this record. No A2 code, judge semantics, or Decision Ledger was
changed in this remediation.

## Remaining acceptance work

The report's external-system and commercial gaps remain open: real PostgreSQL
and deployment qualification, real OAuth/payment/provider integrations,
production rollback and disaster-recovery evidence, formal licensing, and the
current `production_ready=false` / `blocked_by_a2` release state.
