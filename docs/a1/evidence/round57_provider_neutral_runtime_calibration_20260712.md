# Round 57 Provider-Neutral Runtime Calibration

Date: 2026-07-12

## Scope

This calibration exercised the public Python and TypeScript provider adapters,
not provider-specific probe scripts. Secret values were read from user-level
environment variables and were never printed, persisted, or committed.

The bounded small batch covered:

- non-stream text completion;
- streamed text completion;
- one forced tool call;
- normalized usage;
- normalized finish reason.

## Providers

| Backend | Model | Python | TypeScript | Stream | Tool | Usage |
|---|---|---:|---:|---:|---:|---:|
| Local Ollama | `qwen2.5:1.5b` | pass | pass | pass | pass | pass |
| XJTLU OpenAI-compatible relay | `gpt-5.6-sol` | pass | pass | pass | pass | pass |
| Qwen official OpenAI-compatible API | `qwen-plus` | pass | pass | pass | pass | pass |

All text probes returned the expected marker. All tool probes returned one
`emit_marker` call. Both SDKs retained the provider's real finish reason:
Ollama returned `stop` with a tool call, while XJTLU and Qwen returned
`tool_calls`. The shared run/trace contract does not rewrite this difference.

Observed total token counts were non-zero for every provider and execution
mode. Representative bounded latency was approximately 0.35-2.83 seconds per
request. These values are calibration observations, not service guarantees.

## Modality Status

Text is `callable` for all three calibrated model endpoints. Image, audio,
file, and video remain equal first-class SDK input types and provider-local
request envelopes, but stay `discovered` for these exact model endpoints until
a real request succeeds. Protocol shape alone is not treated as model
capability evidence.

## Safety

- No API key value, authorization header, raw response, prompt secret, or
  signed media URL is present in this evidence.
- Real calls used zero retries to avoid accidental duplicate paid requests.
- Provider-specific request and response fields remain in adapter code.
- No A2 judge or A3 dashboard semantics were changed.

## Evidence Binding Gap

The bounded probes were executed through the public SDK adapters, but this
round did not persist private raw provider records. Therefore this public
summary cannot honestly publish `endpoint_sha256`, `evidence_sha256`,
`calibrated_at`, private evidence paths, or response-key bindings derived from
those records. No hashes or paths are fabricated. A later calibration run must
write secret-safe private records first and derive the public capability
records from those exact bytes.

Capability-record constructors now fail closed on empty evidence,
timezone-free or invalid timestamps, unknown capability names, and non-terminal
states such as `discovered`. Python returns an immutable capability mapping;
TypeScript performs the same checks at runtime for plain JavaScript callers.
