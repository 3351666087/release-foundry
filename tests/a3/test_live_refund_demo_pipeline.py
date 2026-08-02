from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
for entry in (ROOT, SDK_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from examples.agents.ollama_refund_agent import (  # noqa: E402
    DEMO_AMOUNT,
    DEMO_ORDER_ID,
    RefundOrderSandbox,
    OllamaRefundAgent,
)
from releasefoundry.model_adapter import ModelResponse, ModelToolCall  # noqa: E402
from scripts.demo.run_live_refund_pipeline import run_pipeline  # noqa: E402


class SequenceAdapter:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, **options):
        assert messages
        assert options["temperature"] == 0
        return self.responses.pop(0)


class ContractAgent:
    def reset(self):
        pass

    def respond(self, prompt):
        assert DEMO_ORDER_ID in prompt
        return {
            "text": f"沙盒退款模拟已完成：订单 {DEMO_ORDER_ID}，金额 {DEMO_AMOUNT} 元。",
            "tool_calls": [{
                "id": "tool-contract-refund",
                "name": "refund_order_sandbox",
                "arguments": {"order_id": DEMO_ORDER_ID, "amount": DEMO_AMOUNT},
                "output": {
                    "receipt_id": "refund_demo_receipt_contract",
                    "status": "approved",
                    "order_id": DEMO_ORDER_ID,
                    "amount": DEMO_AMOUNT,
                    "sandbox": True,
                    "external_payment_mutated": False,
                },
            }],
            "metadata": {"model_inference_real": True, "sandbox": True},
        }


def test_ollama_agent_executes_only_the_sandbox_tool():
    adapter = SequenceAdapter([
        ModelResponse(
            text="",
            tool_calls=[ModelToolCall(
                id="model-tool-call",
                name="refund_order_sandbox",
                arguments={"order_id": DEMO_ORDER_ID, "amount": DEMO_AMOUNT},
            )],
        ),
        ModelResponse(text=f"沙盒模拟：订单 {DEMO_ORDER_ID} 已退款 {DEMO_AMOUNT} 元。"),
    ])
    result = OllamaRefundAgent(adapter=adapter, model="unit-model").respond(
        f"refund {DEMO_ORDER_ID} for {DEMO_AMOUNT}"
    )

    assert result["metadata"]["model_inference_real"] is True
    assert result["metadata"]["external_order_or_payment_access"] is False
    assert result["tool_calls"][0]["name"] == "refund_order_sandbox"
    assert result["tool_calls"][0]["output"]["status"] == "approved"
    assert result["tool_calls"][0]["output"]["external_payment_mutated"] is False


def test_refund_sandbox_rejects_non_demo_orders():
    sandbox = RefundOrderSandbox()
    try:
        sandbox.refund(order_id="real-order", amount=DEMO_AMOUNT)
    except ValueError as error:
        assert "not allowlisted" in str(error)
    else:
        raise AssertionError("non-demo order should have been rejected")


def test_ollama_agent_repairs_a_misleading_real_payment_claim():
    adapter = SequenceAdapter([
        ModelResponse(text=json.dumps({
            "action": "refund_order_sandbox",
            "order_id": DEMO_ORDER_ID,
            "amount": DEMO_AMOUNT,
        })),
        ModelResponse(text=f"模拟订单 {DEMO_ORDER_ID} 的 {DEMO_AMOUNT} 元退款真实发生。"),
    ])
    result = OllamaRefundAgent(adapter=adapter, model="unit-model").respond("refund demo order")

    assert result["metadata"]["final_response_repaired"] is True
    assert "不会修改真实订单或付款" in result["text"]
    assert "真实发生" not in result["text"]


def test_pipeline_joins_a1_trace_and_a2_grade(tmp_path):
    receipt = run_pipeline(tmp_path, agent=ContractAgent)
    run_result = json.loads((tmp_path / "a1_run_result.json").read_text(encoding="utf-8"))
    grade_result = json.loads((tmp_path / "a2_grade_result.json").read_text(encoding="utf-8"))
    case = run_result["cases"][0]
    grade = grade_result["grade_results"][0]

    assert receipt["run_id"] == run_result["run_id"] == grade["run_id"]
    assert receipt["a1"]["tool_call_count"] == 1
    assert receipt["a1"]["trace_event_count"] == 4
    assert receipt["a2"]["judge_count"] == 5
    assert grade["passed"] is True
    assert grade["primary_failure_class"] == "none"
    assert {event["event_type"] for event in case["trace_events"]} == {
        "message",
        "agent_response",
        "tool_call",
        "tool_result",
    }
    assert [event["event_type"] for event in case["trace_events"]] == [
        "message",
        "tool_call",
        "tool_result",
        "agent_response",
    ]
