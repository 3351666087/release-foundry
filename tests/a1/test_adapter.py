import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from ashr_clone.adapter import AgentAdapter, AgentResult  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
