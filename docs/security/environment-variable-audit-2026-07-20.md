# Environment Variable Audit — 2026-07-20

## Scope and handling rules

This audit covers environment-variable names referenced by tracked source,
tests, workflows, and example configuration in the PR #37 integration tree.
It also checks whether each referenced name is present in the current process
environment.

The audit is deliberately **name-only**:

- no environment-variable value was written to this document;
- no secret value was added to Git, test output, or release evidence;
- presence checks record only `set` or `not set`;
- the conservative `secret-likely` classification is based on variable names,
  not on inspecting their values.

## Inventory result

| Measure | Result |
| --- | ---: |
| Referenced environment-variable names | 169 |
| Conservatively classified as secret-likely | 41 |
| Present in the current process environment | 5 |
| Present and secret-likely | 2 |

The five names present in the current process environment were:

- `ASHR_API_KEY`
- `ASHR_SMTP_AUTH_CODE`
- `ASHR_SMTP_FROM`
- `ASHR_SMTP_HOST`
- `ASHR_SMTP_PORT`

Of those names, `ASHR_API_KEY` and `ASHR_SMTP_AUTH_CODE` were classified as
secret-likely. Their values were not read into the audit report and were not
committed.

## Important unavailable integrations

The following important integration variables were not configured in the
audited process:

- `A1_POSTGRES_TEST_DSN`
- `ASHR_LABS_API_KEY`
- `A3_POSTGRES_LIVE`
- `A3_POSTGRES_TEST_HOST`
- `A3_POSTGRES_TEST_PORT`
- `A3_POSTGRES_TEST_USER`
- `A3_POSTGRES_TEST_PASSWORD`
- `A3_POSTGRES_TEST_DATABASE`
- `A3_POSTGRES_TEST_SSLMODE`
- `ASHR_IDENTITY_DELIVERY_LIVE_ADMIN_DSN`
- `ASHR_IDENTITY_DELIVERY_LIVE_DSN`
- `ASHR_IDENTITY_LIFECYCLE_TEST_DSN`
- `DASHSCOPE_API_KEY`
- `GH_TOKEN`
- `GITHUB_TOKEN`
- `POSTGRES_DSN`

Consequences:

- live PostgreSQL was not configured;
- live PostgreSQL tests must not be reported as passed;
- PostgreSQL/live-provider cases that require these variables were skipped or
  were not executed;
- GitHub mutation steps use the authenticated Git/GitHub integration rather
  than a repository-tracked token;
- provider-specific live calibration was not treated as a prerequisite for
  provider-independent local gates.

## Secret and configuration review

The tracked tree and the pending PR #37 changes were checked for accidental
secret material. No newly added or tracked genuine GitHub, OpenAI, AWS,
Google, or Slack token; private key; or JWT was identified.

Configuration examples use placeholders or secret references. The audit does
not claim that every production integration is configured; it establishes
that the local gate run did not depend on undisclosed production credentials
and that missing live integrations are explicitly accounted for.

The following repository checks also completed without a secret or commercial
release blocker:

```text
python scripts/cl_guard.py hygiene
  findings=[]

python scripts/cl_guard.py commercial
  blockers=0
  advisories=0

git diff --check
  passed
```

## Conclusion

The local environment is suitable for the offline and mocked A1/A2/A3 release
gates recorded for PR #37. It is **not** a configured live PostgreSQL or live
provider environment, and this audit does not make that claim.
