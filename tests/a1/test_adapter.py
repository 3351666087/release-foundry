import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

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

    def test_non_json_text_fields_are_normalized_without_adapter_error(self):
        result = AgentAdapter(lambda prompt: {"content": Path("content.txt")}).respond("ignored")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, '"content.txt"')

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
