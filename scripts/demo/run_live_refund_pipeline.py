from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
for entry in (ROOT, SDK_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from examples.agents.ollama_refund_agent import (  # noqa: E402
    DEMO_AMOUNT,
    DEMO_ORDER_ID,
    TOOL_NAME,
    OllamaRefundAgent,
)
from services.judge.runner import grade_run  # noqa: E402
from services.runner.runner import run_agent_batch  # noqa: E402


SCENARIO_ID = "ECOM-REFUND-LIVE-001"
CASE_ID = "case-live-refund-001"
DATASET_ID = "dataset-live-refund-demo"
SCENARIO_PACK = ROOT / "fixtures" / "a3" / "demo" / "live_refund_scenario_pack.json"


def build_case() -> dict[str, Any]:
    return {
        "case_id": CASE_ID,
        "scenario_id": SCENARIO_ID,
        "title": "真实本地模型：沙盒订单退款",
        "family": "ecommerce_refund",
        "prompt": f"请帮我把模拟订单 {DEMO_ORDER_ID} 退款 {DEMO_AMOUNT} 元。",
        "expected": {
            "summary": "先调用沙盒退款工具，再根据真实工具回执回答用户。",
            "tool_calls": [
                {
                    "name": TOOL_NAME,
                    "arguments": {"order_id": DEMO_ORDER_ID, "amount": DEMO_AMOUNT},
                }
            ],
            "final_response_points": [
                f"必须包含订单号 {DEMO_ORDER_ID}",
                f"必须包含退款金额 {DEMO_AMOUNT} 元",
                "必须说明这是沙盒模拟，不是真实资金操作",
            ],
        },
        "metadata": {
            "teaching_demo": True,
            "containerized_agent": True,
            "sandbox": True,
            "contains_real_customer_data": False,
        },
    }


def run_pipeline(output_dir: Path, agent: Any = OllamaRefundAgent) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_result = run_agent_batch(
        agent,
        [build_case()],
        dataset_id=DATASET_ID,
        runner_id="a1-docker-ollama-runner",
        max_workers=1,
        timeout_seconds=180,
    )
    run_result["metadata"].update({
        "local_only": True,
        "containerized_agent": True,
        "model_provider": "ollama",
        "sandbox_tool": TOOL_NAME,
        "external_order_or_payment_access": False,
    })
    case_result = run_result["cases"][0]
    case_result["family"] = "ecommerce_refund"
    case_result["trace_events"] = _project_trace_events(case_result)

    grade = grade_run(
        SCENARIO_ID,
        case_result,
        pack_path=SCENARIO_PACK,
        case_id=CASE_ID,
    )
    grade["run_id"] = run_result["run_id"]
    grade["metadata"] = {
        "deterministic": True,
        "authority": "services.judge.runner.grade_run",
        "source_run_id": run_result["run_id"],
        "sandbox": True,
    }
    grade_fixture = {
        "schema_version": "a2.grade_results.v1",
        "report_id": f"a2_live_refund_{run_result['run_id']}",
        "dataset_id": DATASET_ID,
        "scenario_pack": "fixtures/a3/demo/live_refund_scenario_pack.json",
        "total_cases": 1,
        "passed": 1 if grade["passed"] else 0,
        "failed": 0 if grade["passed"] else 1,
        "grade_results": [grade],
    }

    run_path = output_dir / "a1_run_result.json"
    grade_path = output_dir / "a2_grade_result.json"
    _write_json(run_path, run_result)
    _write_json(grade_path, grade_fixture)
    receipt = {
        "schema_version": "a3.live_refund_pipeline_receipt.v1",
        "run_id": run_result["run_id"],
        "case_id": CASE_ID,
        "a1": {
            "runner": "services.runner.runner.run_agent_batch",
            "status": case_result["status"],
            "trace_event_count": len(case_result["trace_events"]),
            "tool_call_count": len(case_result.get("agent_output", {}).get("tool_calls", [])),
            "artifact_sha256": _file_hash(run_path),
        },
        "a2": {
            "judge": "services.judge.runner.grade_run",
            "passed": grade["passed"],
            "score": grade["score"],
            "primary_failure_class": grade["primary_failure_class"],
            "judge_count": len(grade["judge_results"]),
            "artifact_sha256": _file_hash(grade_path),
        },
        "runtime": {
            "agent": "OllamaRefundAgent",
            "model_inference_real": case_result.get("agent_output", {}).get("metadata", {}).get("model_inference_real") is True,
            "containerized": True,
            "sandbox": True,
            "external_order_or_payment_access": False,
        },
        "outputs": [run_path.name, grade_path.name],
    }
    _write_json(output_dir / "pipeline_receipt.json", receipt)
    return receipt


def _project_trace_events(case_result: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    sequence = 0
    for observation in case_result.get("observations", []):
        role = observation.get("role", "runtime")
        event_type = observation.get("event_type", "observation")
        tool_calls = observation.get("tool_calls", [])

        def append_observation() -> None:
            nonlocal sequence
            events.append({
                "event_id": f"trace-{CASE_ID}-{sequence:02d}",
                "seq": sequence,
                "phase": "dialogue",
                "event_type": event_type,
                "source": "a1-docker-ollama-runner",
                "role": role,
                "content": observation.get("content", ""),
                "status": observation.get("status", "ok"),
                "observation_id": observation.get("observation_id"),
            })
            sequence += 1

        if role != "assistant" or not tool_calls:
            append_observation()
        for call in tool_calls:
            call_id = call.get("call_id") or call.get("id")
            events.append({
                "event_id": f"trace-{CASE_ID}-{sequence:02d}",
                "seq": sequence,
                "phase": "tool",
                "event_type": "tool_call",
                "source": "a1-docker-ollama-runner",
                "role": "agent",
                "content": f"{call.get('name')} {json.dumps(call.get('arguments', {}), ensure_ascii=False, sort_keys=True)}",
                "status": "ok" if not call.get("error") else "error",
                "tool_call_id": call_id,
                "data": {"tool_call": call},
            })
            sequence += 1
            events.append({
                "event_id": f"trace-{CASE_ID}-{sequence:02d}",
                "seq": sequence,
                "phase": "tool",
                "event_type": "tool_result",
                "source": "a1-docker-ollama-runner",
                "role": "tool",
                "content": json.dumps(call.get("output", {}), ensure_ascii=False, sort_keys=True),
                "status": "ok" if not call.get("error") else "error",
                "tool_call_id": call_id,
            })
            sequence += 1
        if role == "assistant" and tool_calls:
            append_observation()
    return events


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Docker Ollama Agent -> A1 Trace -> A2 Judge demo.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".demo-output" / "live-refund")
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)
    receipt = run_pipeline(args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.require_pass and not receipt["a2"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
