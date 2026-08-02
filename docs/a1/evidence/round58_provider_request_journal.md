# A1 Round 58 - Provider Request Journal

## Scope

This round adds durable provider-call journaling to the Python and TypeScript SDK
surfaces. The journal is intended for money-bearing or otherwise non-idempotent
provider operations where a process crash, network ambiguity, streamed partial
response, or duplicate worker must not silently execute the provider request
twice.

## Safety properties

- A request is scoped by tenant, project, provider, model, operation, and a
  request fingerprint.
- Raw idempotency keys, prompts, media bytes, media URLs, local paths,
  credentials, provider URLs, and lease-owner values are not persisted.
- Lease owners and commercial identity dimensions are represented only by
  one-way fingerprints in persisted evidence.
- Restart recovery converts an interrupted active request to `indeterminate`
  and clears its lease before any new execution can be considered.
- Same-process TypeScript duplicates coordinate through a keyed active-run
  fence, so exactly one provider invocation owns the request.
- A stale completion cannot overwrite a newer fenced owner.
- A request that has observed any streamed output cannot be automatically
  retried or reconciled to a retryable state.
- Explicit reconciliation is required for ambiguous non-streamed outcomes.
- Text, image, audio, file, and video requests produce the same public-safe
  modality evidence contract.

## Cross-language boundary

Python and TypeScript expose equivalent behavioral guarantees, but their local
JSON snapshots are currently implementation-private and are **not**
cross-language wire compatible. They use different state vocabularies and
record layouts even though both currently identify the behavioral generation
as `releasefoundry.provider_request_journal.v2`. A Python process must not open a
TypeScript journal file, and a TypeScript process must not open a Python journal
file. A future shared snapshot contract must introduce an explicit
implementation marker or a new canonical schema version plus migration tests
before interchange is claimed.

## Validation

- `python -m pytest -q tests/a1/test_provider_journal.py tests/a1/test_provider_journal_adversarial_round58.py`
  - `24 passed`
- `npm test` in `packages/ts/releasefoundry`
  - `329 passed`, `0 failed`, `0 skipped`, `0 todo`
- `python -m pytest -q tests/a1`
  - initial run: `336 passed`, `1 skipped`, with one generated parity-matrix
    mismatch after the new exports were added
  - the matrix was regenerated with
    `python tests/a1/ts_python_parity_matrix.py --write`
  - the focused parity-matrix test then passed

## Public evidence policy

All committed fixtures use synthetic identifiers and secret-like test values.
No real provider credential, OAuth token, API key, private prompt, media
payload, signed URL, provider request identifier, or customer email is included
in this public evidence.
