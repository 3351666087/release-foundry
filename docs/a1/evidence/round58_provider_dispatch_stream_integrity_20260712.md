# Round 58 Provider Dispatch And Stream Integrity

## Scope

This evidence covers the Python and TypeScript provider request journals and
the shared `ashr.clone.provider_stream.v1` integrity protocol.

## Proven

- Unit behavior: claim, lease, fencing, replay, conflict, expiration,
  indeterminate state, and explicit reconciliation.
- Restart behavior: file-backed in-flight requests are not silently retried
  when provider acceptance is uncertain.
- Stream behavior: monotonic frames, digest chaining, terminal enforcement,
  duplicate idempotency, conflict detection, and tamper rejection.
- Cross-language behavior: pytest starts a real Node process to validate an
  `ashr.clone.provider_stream.v1` snapshot and emit another stream snapshot,
  which Python then validates.
- Journal persistence behavior: Python uses
  `ashr.clone.provider_request_journal.python.v1`; TypeScript uses
  `ashr.clone.provider_request_journal.typescript.v1`. These persistence
  formats are intentionally separate and are not claimed to be mutually
  readable.
- Privacy behavior: snapshots contain content digests only. Test text,
  including Unicode text, is absent from persisted fixtures.
- Distribution behavior: the TypeScript package exports both journal and
  stream subpaths with JavaScript and declaration files; the Python wheel
  includes the complete SDK package.

## Not Proven

- PostgreSQL-backed provider journal coordination.
- Multi-host or multi-region lease consensus.
- Distributed transaction atomicity with queue or usage-ledger writes.
- Provider-native idempotency support.
- Automatic safety of retry after any accepted or partially observed provider
  request. Such requests deliberately become `indeterminate`.

## Verification

```text
npm test
623 passed, 0 failed

npm pack --dry-run
passed; 111 files; provider-request-journal and provider-stream
JavaScript/declaration artifacts included

python -B -m pytest <focused Round 58 tests>
39 passed

python -B -m pytest tests/a1 -q -p no:cacheprovider
1320 passed, 2 skipped in 283.94s

python scripts/cl_guard.py hygiene
passed; zero findings
```

The final audit follow-up binds every persisted stream snapshot to the active
entry ID and fencing token. A streamed success requires a terminal snapshot
under that active fence; unbound, mismatched, and partial snapshots fail
closed. The TypeScript loader also validates persisted snapshots strictly,
including canonical fields, SHA-256 fingerprints, safe integer counters,
timestamps, evidence flags, all five modality fields, persistence capability
metadata, usage/completion/error evidence, and state/lease/terminal
invariants. A failed persistence write no longer permanently poisons the
in-process write chain; later writes can proceed after the failed operation is
reported.

## Branch Boundary

The only published A1 development tree is
`origin/codex/a1-local-sdk-runner`. The local worktree branch name is not a
second publication target.
