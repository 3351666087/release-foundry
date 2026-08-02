import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from releasefoundry import (  # noqa: E402
    AgentInput,
    ModelAdapterError,
    ModelHTTPResponse,
    ModelInputPart,
    ProviderNeutralModelAdapter,
)
from releasefoundry.model_adapter import create_capability_calibration  # noqa: E402


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout, stream):
        self.calls.append((method, url, headers, json.loads(body), timeout, stream))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ModelAdapterTests(unittest.TestCase):
    def test_openai_complete_normalizes_text_tools_usage_and_finish(self):
        transport = RecordingTransport([ModelHTTPResponse(200, {
            "model": "commercial-model",
            "choices": [{"message": {"content": "hello", "tool_calls": [
                {"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"x"}'}}
            ]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        })])
        adapter = ProviderNeutralModelAdapter.for_openai_compatible(
            model="commercial-model", base_url="https://models.example/v1", api_key="sk-supersecret123", transport=transport
        )
        result = adapter.complete(["hello"], tools=[{"type": "function", "function": {"name": "lookup"}}], timeout=9)
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.tool_calls[0].arguments, {"q": "x"})
        self.assertEqual(result.usage.total_tokens, 7)
        self.assertEqual(result.finish_reason, "tool_calls")
        self.assertEqual(transport.calls[0][1], "https://models.example/v1/chat/completions")
        self.assertEqual(transport.calls[0][4], 9)

    def test_ollama_complete_and_options(self):
        transport = RecordingTransport([ModelHTTPResponse(200, {
            "model": "qwen", "message": {"content": "local"}, "done": True,
            "prompt_eval_count": 6, "eval_count": 2,
        })])
        adapter = ProviderNeutralModelAdapter.for_ollama(model="qwen", transport=transport)
        result = adapter.complete(["hi"], temperature=0)
        self.assertEqual(result.text, "local")
        self.assertEqual(result.usage.total_tokens, 8)
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(transport.calls[0][3]["options"], {"temperature": 0})

    def test_all_modalities_are_preserved_and_agent_input_is_accepted(self):
        transport = RecordingTransport([ModelHTTPResponse(200, {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})])
        agent_input = AgentInput.from_parts([
            {"type": "text", "text": "inspect"},
            {"type": "image", "url": "https://example.test/i.png"},
            {"type": "audio", "data": "YQ==", "mime_type": "audio/wav"},
            {"type": "file", "url": "https://example.test/f.pdf", "filename": "f.pdf"},
            {"type": "video", "url": "https://example.test/v.mp4"},
        ])
        ProviderNeutralModelAdapter.for_openai_compatible(
            model="m", base_url="https://models.example/v1", transport=transport
        ).complete([agent_input])
        parts = transport.calls[0][3]["messages"][0]["content"]
        self.assertEqual([part["type"] for part in parts], ["text", "image_url", "input_audio", "input_file", "input_video"])
        self.assertEqual(parts[2]["data"], "YQ==")

    def test_openai_sse_stream_handles_split_frames_tool_fragments_usage_and_done(self):
        events = [
            b'data: {"choices":[{"delta":{"content":"hel"},"finish_reason":null}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"lo","tool_calls":[{"index":0,"id":"c1","function":{"name":"lookup","arguments":"{\\"q\\":"}}]},"finish_reason":null}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"x\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\ndata: [DONE]\n\n',
        ]
        transport = RecordingTransport([ModelHTTPResponse(200, events)])
        chunks = list(ProviderNeutralModelAdapter.for_openai_compatible(
            model="m", base_url="https://models.example/v1", transport=transport
        ).stream(["hi"]))
        self.assertEqual("".join(chunk.text for chunk in chunks), "hello")
        self.assertEqual(chunks[1].tool_calls[0].arguments, '{"q":')
        self.assertEqual(chunks[2].tool_calls[0].id, "c1")
        self.assertEqual(chunks[2].tool_calls[0].name, "lookup")
        self.assertEqual(chunks[2].tool_calls[0].arguments, '{"q":"x"}')
        self.assertEqual(chunks[2].finish_reason, "tool_calls")
        self.assertEqual(chunks[3].usage.total_tokens, 5)

    def test_ollama_ndjson_stream(self):
        body = [
            '{"message":{"content":"a"},"done":false}\n',
            '{"message":{"content":"b"},"done":true,"done_reason":"stop","prompt_eval_count":1,"eval_count":2}\n',
        ]
        transport = RecordingTransport([ModelHTTPResponse(200, body)])
        chunks = list(ProviderNeutralModelAdapter.for_ollama(model="qwen", transport=transport).stream(["hi"]))
        self.assertEqual("".join(chunk.text for chunk in chunks), "ab")
        self.assertEqual(chunks[-1].usage.total_tokens, 3)

    def test_retry_status_timeout_and_non_retryable_errors(self):
        transport = RecordingTransport([
            ModelHTTPResponse(429, "limited"),
            ModelHTTPResponse(200, {"choices": [{"message": {"content": "ok"}, "finish_reason": "max_tokens"}]}),
        ])
        adapter = ProviderNeutralModelAdapter.for_openai_compatible(
            model="m", base_url="https://models.example/v1", transport=transport, max_retries=1, retry_backoff_seconds=0
        )
        self.assertEqual(adapter.complete(["x"]).finish_reason, "max_tokens")
        self.assertEqual(len(transport.calls), 2)

        bad = RecordingTransport([ModelHTTPResponse(400, "bad")])
        with self.assertRaises(ModelAdapterError) as raised:
            ProviderNeutralModelAdapter.for_openai_compatible(
                model="m", base_url="https://models.example/v1", transport=bad, max_retries=3
            ).complete(["x"])
        self.assertEqual(raised.exception.kind, "http")
        self.assertEqual(len(bad.calls), 1)

        timed = RecordingTransport([TimeoutError("Authorization: Bearer sk-supersecret123")])
        with self.assertRaises(ModelAdapterError) as raised:
            ProviderNeutralModelAdapter.for_ollama(model="m", transport=timed, max_retries=0).complete(["x"])
        self.assertEqual(raised.exception.kind, "timeout")
        self.assertNotIn("supersecret", str(raised.exception))

    def test_finish_reason_preserves_provider_truth_independent_of_tool_calls(self):
        transport = RecordingTransport([
            ModelHTTPResponse(200, {
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }],
                    },
                    "finish_reason": "stop",
                }],
            }),
            ModelHTTPResponse(200, {
                "choices": [{
                    "message": {"content": "bounded"},
                    "finish_reason": "model_length",
                }],
            }),
        ])
        adapter = ProviderNeutralModelAdapter.for_openai_compatible(
            model="m", base_url="https://models.example/v1", transport=transport
        )
        tool_result = adapter.complete(["x"])
        unknown_result = adapter.complete(["x"])
        self.assertEqual(tool_result.finish_reason, "stop")
        self.assertEqual(len(tool_result.tool_calls), 1)
        self.assertEqual(unknown_result.finish_reason, "model_length")

    def test_capability_calibration_is_endpoint_model_and_evidence_scoped(self):
        record = create_capability_calibration(
            provider="ollama",
            model="qwen2.5:1.5b",
            base_url="http://localhost:11434/",
            calibrated_at="2026-07-12T00:00:00Z",
            evidence=b"redacted calibration facts",
            capabilities={"text": "callable", "stream": "callable", "tools": "callable", "usage": "callable"},
        )
        self.assertEqual(record.provider, "ollama")
        self.assertEqual(record.model, "qwen2.5:1.5b")
        self.assertEqual(len(record.endpoint_sha256), 64)
        self.assertEqual(len(record.evidence_sha256), 64)
        self.assertEqual(record.capabilities["tools"], "callable")
        self.assertNotIn("image", record.capabilities)
        with self.assertRaises(TypeError):
            record.capabilities["tools"] = "failed"

    def test_capability_calibration_rejects_weak_evidence_metadata(self):
        base = {
            "provider": "ollama",
            "model": "qwen2.5:1.5b",
            "base_url": "http://localhost:11434",
            "calibrated_at": "2026-07-12T00:00:00Z",
            "evidence": "facts",
            "capabilities": {"text": "callable"},
        }
        for overrides in (
            {"capabilities": {"text": "discovered"}},
            {"capabilities": {"text": "arbitrary"}},
            {"evidence": ""},
            {"evidence": b""},
            {"calibrated_at": "2026-07-12T00:00:00"},
            {"calibrated_at": "not-a-timestamp"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                create_capability_calibration(**(base | overrides))

    def test_stream_is_not_retried_after_response_is_returned(self):
        def broken_stream():
            yield 'data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}\n\n'
            raise ConnectionError("later")

        transport = RecordingTransport([ModelHTTPResponse(200, broken_stream())])
        stream = ProviderNeutralModelAdapter.for_openai_compatible(
            model="m", base_url="https://models.example/v1", transport=transport, max_retries=3
        ).stream(["x"])
        self.assertEqual(next(stream).text, "first")
        with self.assertRaises(ModelAdapterError):
            next(stream)
        self.assertEqual(len(transport.calls), 1)

    def test_malformed_responses_and_configuration_are_normalized(self):
        transport = RecordingTransport([ModelHTTPResponse(200, "not-json")])
        with self.assertRaises(ModelAdapterError) as raised:
            ProviderNeutralModelAdapter.for_openai_compatible(
                model="m", base_url="https://models.example/v1", transport=transport
            ).complete(["x"])
        self.assertEqual(raised.exception.kind, "malformed_response")
        with self.assertRaises(ModelAdapterError):
            ProviderNeutralModelAdapter(provider="other", model="m", base_url="https://x")
        with self.assertRaises(ModelAdapterError):
            ModelInputPart.from_value({"type": "binary", "data": "x"})


if __name__ == "__main__":
    unittest.main()
