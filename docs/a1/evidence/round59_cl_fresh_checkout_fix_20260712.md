# Round 59 CL Fresh-Checkout Repair

Date: 2026-07-12

## Failure

PR 36 run `29191539967` failed `Python A1/A2 contracts` because
`tests/a1/test_provider_stream.py` imported
`packages/ts/ashr-clone/dist/provider-stream.js` without guaranteeing that a
clean checkout had built the TypeScript package.

The previous local result was invalid as fresh-setup evidence because an
ignored local `dist/` directory already existed.

## Repair

- The Python CL job now provisions Node 24, installs the locked TypeScript
  dependencies, and builds the TypeScript SDK before Python contracts run.
- The interoperability test also builds the TypeScript package when its
  required generated module is absent. This keeps direct pytest execution
  reproducible after the locked TypeScript dependencies are installed.
- Python SDK `build/` and `*.egg-info/` output is now ignored and remains
  excluded from commits.

No generated TypeScript `dist/` content is committed. No A2 judge semantics or
A3 dashboard/report behavior changed.

## Verification

With `packages/ts/ashr-clone/dist/` removed first:

```text
python -B -m pytest tests/a1/test_provider_stream.py -q -p no:cacheprovider
10 passed in 3.83s
```

CI-equivalent validation:

```text
python -m compileall packages services scripts tests
python -B -m pytest tests/a1 tests/a2 tests/integration/test_a1_large_saas_migration.py -q -p no:cacheprovider
1515 passed, 2 skipped in 277.89s
```

`git diff --check` also passed.
