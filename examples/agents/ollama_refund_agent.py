from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from typing import Any, Mapping

from ashr_clone.model_adapter import ModelResponse, ProviderNeutralModelAdapter


DEMO_ORDER_ID = "order_demo_123"
DEMO_AMOUNT = 42
TOOL_NAME = "refund_order_sandbox"


@dataclass(slots=True)
class RefundOrderSandbox:
    """In-memory refund tool. It never connects to an order or payment system."""

    order_id: str = DEMO_ORDER_ID
    refundable_amount: int = DEMO_AMOUNT
    refunded: bool = False

    def refund(self, *, order_id: str, amount: int | float) -> dict[str, Any]:
        normalized_amount = int(amount) if float(amount).is_integer() else float(amount)
        if order_id != self.order_id:
            raise ValueError("sandbox order is not allowlisted")
        if normalized_amount != self.refundable_amount:
            raise ValueError("sandbox refund amount does not match the demo order")
        if self.refunded:
            return self._receipt(normalized_amount, duplicate=True)
        self.refunded = True
        return self._receipt(normalized_amount, duplicate=False)

    def _receipt(self, amount: int | float, *, duplicate: bool) -> dict[str, Any]:
        digest = sha256(f"{self.order_id}:{amount}:refund-demo".encode("utf-8")).hexdigest()[:12]
        return {
            "receipt_id": f"refund_demo_receipt_{digest}",
            "status": "approved",
            "order_id": self.order_id,
            "amount": amount,
            "currency": "CNY",
            "sandbox": True,
            "duplicate": duplicate,
            "external_payment_mutated": False,
        }


class OllamaRefundAgent:
    """A real local-model agent with one tightly scoped sandbox tool."""

    def __init__(
        self,
        *,
        adapter: ProviderNeutralModelAdapter | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        model_name = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
        endpoint = base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.adapter = adapter or ProviderNeutralModelAdapter.for_ollama(
            model=model_name,
            base_url=endpoint,
            timeout=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120")),
            max_retries=1,
        )
        self.model = model_name
        self.sandbox = RefundOrderSandbox()

    def reset(self) -> None:
        self.sandbox = RefundOrderSandbox()

    def respond(self, prompt: str) -> dict[str, Any]:
        decision, decision_attempts = self._decide(prompt)
        order_id = str(decision.get("order_id") or "")
        amount = _number(decision.get("amount"))
        receipt = self.sandbox.refund(order_id=order_id, amount=amount)
        call_id = "tool_" + sha256(
            json.dumps({"name": TOOL_NAME, "order_id": order_id, "amount": amount}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        tool_call = {
            "id": call_id,
            "name": TOOL_NAME,
            "arguments": {"order_id": order_id, "amount": amount},
            "output": receipt,
        }
        final_text, final_repaired = self._summarize(prompt, receipt)
        return {
            "text": final_text,
            "tool_calls": [tool_call],
            "metadata": {
                "agent": "ollama-refund-agent",
                "provider": "ollama",
                "model": self.model,
                "model_inference_real": True,
                "decision_model_attempts": decision_attempts,
                "final_response_repaired": final_repaired,
                "sandbox": True,
                "external_order_or_payment_access": False,
            },
        }

    def _decide(self, prompt: str) -> tuple[dict[str, Any], int]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are a refund workflow agent operating only on synthetic demo data. "
                    "For a valid request, call refund_order_sandbox exactly once. Never claim access to a real order, bank, or payment system."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\nReturn a tool call, or one JSON object only: "
                    f'{{"action":"{TOOL_NAME}","order_id":"{DEMO_ORDER_ID}","amount":{DEMO_AMOUNT}}}.'
                ),
            },
        ]
        last_text = ""
        for attempt in range(1, 3):
            response = self.adapter.complete(
                messages,
                tools=[_refund_tool_schema()],
                temperature=0,
                num_predict=160,
            )
            decision = _decision_from_response(response)
            if decision is not None:
                return decision, attempt
            last_text = response.text
            messages.append({"role": "assistant", "content": response.text})
            messages.append({
                "role": "user",
                "content": (
                    "The previous response was not a usable tool decision. Return only the required JSON object "
                    f"for {TOOL_NAME}, {DEMO_ORDER_ID}, and amount {DEMO_AMOUNT}."
                ),
            })
        raise ValueError(f"local model did not produce a valid sandbox tool decision: {_safe_excerpt(last_text)}")

    def _summarize(self, prompt: str, receipt: Mapping[str, Any]) -> tuple[str, bool]:
        response = self.adapter.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Write one concise Chinese customer response based only on the sandbox tool result. "
                        "Include the order id, amount, and explicitly say this is a sandbox simulation."
                    ),
                },
                {"role": "user", "content": prompt},
                {"role": "tool", "name": TOOL_NAME, "content": json.dumps(receipt, ensure_ascii=False, sort_keys=True)},
            ],
            temperature=0,
            num_predict=120,
        )
        text = response.text.strip()
        required = (DEMO_ORDER_ID, str(DEMO_AMOUNT))
        unsafe_real_claims = ("真实发生", "真实退款", "真实到账", "实际到账", "真实资金", "real payment")
        if (
            text
            and all(item in text for item in required)
            and any(marker in text for marker in ("沙盒", "模拟", "demo"))
            and not any(marker in text.lower() for marker in unsafe_real_claims)
        ):
            return text, False
        return (
            f"沙盒退款模拟已完成：订单 {DEMO_ORDER_ID}，金额 {DEMO_AMOUNT} 元。"
            "该结果仅用于课堂演示，不会修改真实订单或付款。",
            True,
        )


def _refund_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Refund one allowlisted synthetic demo order in memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "enum": [DEMO_ORDER_ID]},
                    "amount": {"type": "number", "enum": [DEMO_AMOUNT]},
                },
                "required": ["order_id", "amount"],
                "additionalProperties": False,
            },
        },
    }


def _decision_from_response(response: ModelResponse) -> dict[str, Any] | None:
    for call in response.tool_calls:
        if call.name == TOOL_NAME:
            arguments = _object(call.arguments)
            if _valid_decision(arguments):
                return arguments
    parsed = _first_json_object(response.text)
    if parsed and parsed.get("action") == TOOL_NAME and _valid_decision(parsed):
        return parsed
    return None


def _valid_decision(value: Mapping[str, Any]) -> bool:
    try:
        return str(value.get("order_id")) == DEMO_ORDER_ID and _number(value.get("amount")) == DEMO_AMOUNT
    except (TypeError, ValueError):
        return False


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _first_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _number(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _safe_excerpt(text: str) -> str:
    return " ".join(str(text).split())[:120]
