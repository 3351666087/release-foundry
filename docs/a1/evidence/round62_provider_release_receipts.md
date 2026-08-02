# Round 62 Provider Execution And Release Receipts

Date: 2026-07-13

Round 62 adds cross-language tamper-evident provider receipts and a unified A1 release receipt. Public fixtures contain hashes and safe response shapes only; raw requests, responses, endpoints, request IDs, and credentials remain in ignored private evidence.

## Successful five-modality evidence

| Modality | Provider/runtime | Model/path | Result |
|---|---|---|---|
| text | XJTLU relay | `gpt-5.6-sol` | HTTP 200 with usage |
| text | Qwen official / Ollama local | `qwen-plus` / `qwen2.5:1.5b` | HTTP 200 |
| image | Qwen official | `qwen-vl-max` | HTTP 200 |
| audio | local OpenAI Whisper | `tiny`, CPU | non-empty transcript, one segment |
| file | Qwen official | extracted document input | HTTP 200 |
| video | Qwen official | `qwen3.7-plus`, documented `video_url` | HTTP 200 |

The audio proof uses a deterministic 3.76 second mono PCM speech fixture and open-source Whisper `tiny`. It proves A1 audio execution, not Qwen audio availability. Qwen native audio remained blocked by `Throttling.AllocationQuota`. XJTLU text is callable: five matrix models returned 200, while intermittent 502s indicate upstream routing instability. XJTLU `gpt-image-2` returned 502 through image-generation and Responses paths and remains failed/discovered. The earlier Qwen video failure was invalid media/protocol; a standard official MP4 succeeded.

Each receipt binds normalized endpoint, request, response, private evidence, invocation/completion time, optional hashed request ID, source SHA, release candidate, and previous receipt SHA-256. Failed receipts cannot claim capabilities. Python, TypeScript, and Go share a fixed UTF-8/HTML/timezone vector.

Public artifacts are `tests/a1/fixtures/round62_provider_execution_receipts.json` and `tests/a1/fixtures/round62_a1_release_receipt.json`. The release receipt binds baseline `5dd6a898a6771eaf67bf39246f256b579b4d2211` and evidence from Rounds 57, 60, and 61. It is intentionally a source-candidate receipt, not an impossible self-referential containing-commit claim.

Verification: Python provider evidence `12 passed`; TypeScript `639 passed`; Go tests/vet passed; package contains 117 files including provider-evidence JS and declarations. A hard gate requires successful text/image/audio/file/video coverage and rejects private fields or secret-like material.
