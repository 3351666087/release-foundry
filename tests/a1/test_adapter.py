import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from ashr_clone import AGENT_INPUT_SCHEMA_VERSION, AgentInput, to_a2_judge_run  # noqa: E402
from ashr_clone.adapter import AGENT_TURN_SCHEMA_VERSION, AgentAdapter, AgentAdapterError, AgentResult  # noqa: E402
from ashr_clone.types import ToolCall  # noqa: E402


class RespondAgent:
    def __init__(self):
        self.prompts = []
        self.reset_count = 0

    def respond(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        return {"content": f"answer: {prompt}", "tool_calls": [{"name": "lookup", "arguments": {"q": prompt}}]}

    def reset(self):
        self.reset_count += 1


class AsyncRespondAgent:
    def __init__(self):
        self.reset_count = 0

    async def respond(self, prompt, **kwargs):
        await asyncio.sleep(0)
        return {"choices": [{"message": {"content": f"async answer: {prompt}", "tool_calls": [{"id": "call-1", "function": {"name": "search"}}]}}]}

    async def reset(self):
        await asyncio.sleep(0)
        self.reset_count += 1


class AgentAdapterTests(unittest.TestCase):
    def test_agent_input_to_dict_is_json_safe_and_preserves_media_parts(self):
        agent_input = AgentInput.from_parts(
            [
                {"type": "text", "text": "Describe this file."},
                {"type": "image", "path": Path("fixtures/image.png"), "mimeType": "image/png"},
                {"type": "audio", "url": "https://example.invalid/audio.wav", "mime_type": "audio/wav"},
                {"type": "file", "path": Path("fixtures/spec.pdf"), "name": "spec.pdf", "mime_type": "application/pdf"},
            ],
            metadata={"labels": {"b", "a"}},
        )
        payload = agent_input.to_dict()
        self.assertEqual(payload["schema_version"], AGENT_INPUT_SCHEMA_VERSION)
        self.assertEqual(payload["text"], "Describe this file.")
        self.assertEqual(payload["parts"][1]["type"], "image")
        self.assertEqual(payload["parts"][1]["path"], "fixtures\\image.png" if "\\" in str(Path("fixtures/image.png")) else "fixtures/image.png")
        self.assertEqual(payload["parts"][1]["mime_type"], "image/png")
        self.assertEqual(payload["parts"][2]["type"], "audio")
        self.assertEqual(payload["parts"][3]["type"], "file")
        self.assertEqual(payload["metadata"]["labels"], ["a", "b"])
        self.assertIsInstance(json.dumps(payload), str)

    def test_respond_agent_normalizes_text_tools_and_latency(self):
        agent = RespondAgent()
        adapter = AgentAdapter(agent, name="local-test-agent")
        result = adapter.respond("hello", temperature=0)
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "answer: hello")
        self.assertEqual(result.tool_calls, [{"name": "lookup", "arguments": {"q": "hello"}}])
        self.assertEqual(result.metadata["adapter_name"], "local-test-agent")
        self.assertEqual(result.metadata["style"], "respond")
        self.assertIs(adapter.last_result, result)
        self.assertEqual(adapter.history, [result])

    def test_respond_input_passes_envelope_without_breaking_text_default(self):
        seen = []

        def agent(prompt, **kwargs):
            seen.append((prompt, kwargs))
            return {"content": "ok"}

        adapter = AgentAdapter(agent)
        plain = adapter.respond("hello", mode="text")
        multimodal = adapter.respond_input(
            AgentInput.from_parts(
                [{"type": "text", "text": "look"}, {"type": "image", "path": "fixtures/chart.png", "mime_type": "image/png"}],
                text="look",
                metadata={"case_id": "case-1"},
            ),
            mode="request",
        )
        self.assertEqual(plain.text, "ok")
        self.assertEqual(seen[0], ("hello", {"mode": "text"}))
        envelope, kwargs = seen[1]
        self.assertEqual(kwargs, {"mode": "request"})
        self.assertEqual(envelope["schema_version"], AGENT_INPUT_SCHEMA_VERSION)
        self.assertEqual(envelope["text"], "look")
        self.assertEqual(envelope["parts"][1]["type"], "image")
        self.assertEqual(multimodal.metadata["style"], "callable:request")

    def test_keyword_input_style_passes_envelope_as_named_argument(self):
        class KeywordAgent:
            def __init__(self):
                self.kwargs = None

            def respond(self, **kwargs):
                self.kwargs = kwargs
                return "keyword ok"

        agent = KeywordAgent()
        result = AgentAdapter(agent, input_style="keyword").respond("hello", input_metadata={"source": "unit"}, extra=True)
        self.assertEqual(result.text, "keyword ok")
        self.assertEqual(agent.kwargs["extra"], True)
        self.assertEqual(agent.kwargs["agent_input"]["schema_version"], AGENT_INPUT_SCHEMA_VERSION)
        self.assertEqual(agent.kwargs["agent_input"]["text"], "hello")
        self.assertEqual(agent.kwargs["agent_input"]["metadata"], {"source": "unit"})

    def test_reset_calls_wrapped_agent_when_available(self):
        agent = RespondAgent()
        adapter = AgentAdapter(agent)
        self.assertTrue(adapter.reset())
        self.assertEqual(agent.reset_count, 1)

    def test_callable_and_async_callable_styles_are_supported(self):
        def sync_agent(prompt, **kwargs):
            return {"message": {"content": f"sync {prompt}"}}

        async def async_agent(prompt, **kwargs):
            await asyncio.sleep(0)
            return f"async {prompt}"

        self.assertEqual(AgentAdapter(sync_agent).respond("one").text, "sync one")
        self.assertEqual(AgentAdapter(async_agent).respond("two").text, "async two")

    def test_errors_are_captured_without_raising_by_default(self):
        def failing_agent(prompt):
            raise ValueError(f"bad prompt: {prompt}")

        result = AgentAdapter(failing_agent).respond("boom")
        self.assertFalse(result.ok)
        self.assertEqual(result.error["type"], "ValueError")

    def test_existing_agent_result_is_copied_before_adapter_metadata_is_added(self):
        original = AgentResult(text="already normalized", tool_calls=[{"name": "tool"}], metadata={"source": "fixture"})
        result = AgentAdapter(lambda prompt: original).respond("ignored")
        self.assertIsNot(result, original)
        self.assertEqual(result.metadata["style"], "callable")
        self.assertNotIn("style", original.metadata)

    def test_callable_agent_with_non_callable_respond_attribute_uses_call(self):
        class CallableAgent:
            respond = "not callable"

            def __call__(self, prompt):
                return f"called: {prompt}"

        result = AgentAdapter(CallableAgent()).respond("hello")
        self.assertEqual(result.text, "called: hello")
        self.assertEqual(result.metadata["style"], "callable")

    def test_agent_result_to_dict_is_json_safe(self):
        result = AgentResult(text=Path("answer.txt"), tool_calls=[{"name": "local", "output": Path("not-json")}], metadata={"labels": {"b", "a"}})
        payload = result.to_dict()
        self.assertEqual(payload["schema_version"], AGENT_TURN_SCHEMA_VERSION)
        self.assertEqual(payload["text"], "answer.txt")
        self.assertEqual(payload["tool_calls"][0]["output"], "not-json")
        self.assertEqual(payload["metadata"]["labels"], ["a", "b"])
        self.assertIsInstance(json.dumps(payload), str)

    def test_agent_result_projects_to_a2_judge_run_shape(self):
        result = AgentResult(
            text="Three grounded bullets.",
            tool_calls=[{"name": "file.read", "arguments": {"path": "fixtures/a2/notes/launch-review.md"}, "call_id": "call-1"}],
        )
        payload = to_a2_judge_run(result, expected_keywords=("grounded",), forbidden_keywords=("hallucinated",))
        self.assertEqual(payload["final_response"], "Three grounded bullets.")
        self.assertEqual(payload["expected_keywords"], ["grounded"])
        self.assertEqual(payload["forbidden_keywords"], ["hallucinated"])
        self.assertEqual(payload["tool_calls"][0]["id"], "call-1")
        self.assertEqual(payload["tool_calls"][0]["tool"], "file.read")
        self.assertEqual(payload["tool_calls"][0]["args"], {"path": "fixtures/a2/notes/launch-review.md"})
        self.assertEqual(payload["tool_calls"][0]["name"], "file.read")
        self.assertEqual(payload["tool_calls"][0]["arguments"], {"path": "fixtures/a2/notes/launch-review.md"})
        self.assertIsInstance(json.dumps(payload), str)

    def test_a2_projection_extracts_text_from_multimodal_content_parts(self):
        payload = to_a2_judge_run(
            {
                "text": [{"type": "text", "text": "Grounded answer."}, {"type": "image", "url": "https://example.invalid/chart.png"}],
                "tool_calls": [{"name": "file.read", "arguments": {"path": "fixtures/a2/notes/launch-review.md"}}],
            }
        )
        self.assertEqual(payload["final_response"], "Grounded answer.")
        self.assertEqual(payload["tool_calls"][0]["tool"], "file.read")

    def test_a2_judge_projection_accepts_agent_output_mapping(self):
        payload = to_a2_judge_run({"text": Path("answer.txt"), "tool_calls": [{"tool": "search", "args": {"tags": {"b", "a"}}}]})
        self.assertEqual(payload["final_response"], "answer.txt")
        self.assertEqual(payload["tool_calls"][0]["tool"], "search")
        self.assertEqual(payload["tool_calls"][0]["args"], {"tags": ["a", "b"]})

    def test_non_json_text_fields_are_normalized_without_adapter_error(self):
        result = AgentAdapter(lambda prompt: {"content": Path("content.txt")}).respond("ignored")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, '"content.txt"')

    def test_content_parts_outputs_extract_text_without_json_blob(self):
        result = AgentAdapter(
            lambda prompt: {
                "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "image", "url": "https://example.invalid/image.png"},
                    {"type": "text", "text": "second"},
                ]
            }
        ).respond("ignored")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "first\nsecond")

    def test_adapter_error_payload_and_kwargs_are_redacted(self):
        def failing_agent(prompt, resource_url=None):
            bearer = "Bearer " + "abc.def-123"
            token = "tp_" + "secret123"
            email = "owner" + "@example.com"
            query = "token" + "=abc"
            raise ValueError(f"bad {bearer} {token} {email} https://signed.invalid/file.png?{query}")

        result = AgentAdapter(failing_agent).respond("boom", resource_url="https://private.invalid/audio.wav?" + "X-Amz-" + "Signature=abc")
        self.assertFalse(result.ok)
        message = result.error["message"]
        self.assertNotIn("abc.def-123", message)
        self.assertNotIn("tp_" + "secret123", message)
        self.assertNotIn("owner" + "@example.com", message)
        self.assertNotIn("token" + "=abc", message)
        self.assertEqual(result.metadata["kwargs"]["resource_url"], "https://private.invalid/audio.wav?[redacted]")

    def test_tool_call_to_dict_is_json_safe_directly(self):
        payload = ToolCall(name="local", output=Path("tool-output.txt"), arguments={"labels": {"b", "a"}}).to_dict()
        self.assertEqual(payload["output"], "tool-output.txt")
        self.assertEqual(payload["arguments"]["labels"], ["a", "b"])
        self.assertIsInstance(json.dumps(payload), str)

    def test_raise_errors_wraps_reset_failure_and_preserves_respond_exception(self):
        class FailingResetAgent:
            def reset(self):
                raise RuntimeError("reset boom")

            def respond(self, prompt):
                raise ValueError("respond boom")

        adapter = AgentAdapter(FailingResetAgent(), raise_errors=True)
        with self.assertRaises(AgentAdapterError):
            adapter.reset()
        with self.assertRaises(ValueError):
            adapter.respond("boom")


class AsyncAgentAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_respond_and_async_reset(self):
        agent = AsyncRespondAgent()
        adapter = AgentAdapter(agent)
        result = await adapter.arespond("hello")
        reset_ok = await adapter.areset()
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "async answer: hello")
        self.assertEqual(result.tool_calls, [{"name": "search", "arguments": {}, "call_id": "call-1"}])
        self.assertTrue(reset_ok)
        self.assertEqual(agent.reset_count, 1)

    async def test_async_respond_input_passes_envelope(self):
        async def async_agent(prompt, **kwargs):
            await asyncio.sleep(0)
            return {"content": prompt["text"], "metadata": {"mode": kwargs["mode"]}}

        result = await AgentAdapter(async_agent).arespond_input(AgentInput.from_text("async envelope"), mode="multi")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "async envelope")
        self.assertEqual(result.metadata["mode"], "multi")
        self.assertEqual(result.metadata["style"], "callable:request")

    async def test_sync_methods_can_wrap_async_agent_inside_running_loop(self):
        agent = AsyncRespondAgent()
        adapter = AgentAdapter(agent)
        result = adapter.respond("inside-loop")
        reset_ok = adapter.reset()
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "async answer: inside-loop")
        self.assertTrue(reset_ok)
        self.assertEqual(agent.reset_count, 1)


if __name__ == "__main__":
    unittest.main()
