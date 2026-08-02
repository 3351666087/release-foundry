# Contributing to ReleaseFoundry

Thank you for contributing to ReleaseFoundry. Bug reports, documentation fixes,
tests, and focused implementation changes are welcome.

## Before You Start

- Search existing issues before opening a new one.
- Open an issue before starting a large change or a change to release authority,
  evidence formats, public APIs, or cross-language contracts.
- Never commit credentials, customer data, production evidence, or unredacted
  logs. Use synthetic fixtures for tests and examples.
- Follow the fail-closed release semantics described in the
  [README](README.md).

Security vulnerabilities must be reported through the private process in
[SECURITY.md](SECURITY.md), not through a public issue.

## Development Setup

Use Python 3.12 and Node.js 24. Go 1.22, Rust stable, Docker, and Chromium are
needed only for the parts of the repository that use them. The complete setup
and local product instructions are in the [Quickstart](README.md#quickstart).

## Making a Change

1. Create a focused branch from `main`.
2. Keep generated evidence deterministic and regenerate it with the owning
   script instead of editing derived hashes by hand.
3. Add or update tests for behavioral changes.
4. Run the checks relevant to the files you changed.
5. Open a pull request that explains the behavior, risk, and verification.

## Verification

Start with the repository guards and the suite closest to your change:

```bash
python scripts/cl_guard.py hygiene
python scripts/cl_guard.py commercial
python -B -m pytest tests/release -q -p no:cacheprovider
node --test tests/a3/*.mjs
npm test --prefix packages/ts/releasefoundry
(cd packages/go/releasefoundry && go test ./...)
(cd packages/rust/releasefoundry-runtime-verify && cargo test --quiet)
npm run check --prefix apps/webapp
```

Run the broader contract matrix documented in the
[Quickstart](README.md#quickstart) when a change crosses packages, evidence
formats, or release boundaries. Pull requests must pass the GitHub `CL Gate`.

## Pull Request Checklist

- The change is narrowly scoped and does not contain secrets or private data.
- Public behavior and migration impact are documented.
- Tests cover success, failure, and fail-closed behavior where applicable.
- Generated fixtures and their integrity metadata are consistent.
- New dependencies have a clear purpose and compatible license.

By submitting a contribution, you agree that it is licensed under the
[Apache License 2.0](LICENSE).
