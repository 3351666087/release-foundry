const judgeLabels: Record<string, { zh: string; en: string; detailZh: string; detailEn: string }> = {
  a2_contract_judge: {
    zh: "退款工具契约",
    en: "Refund tool contract",
    detailZh: "检查 Agent 是否真的调用了退款工具，而不是只在文字里说成功。",
    detailEn: "Checks that the agent actually called the refund tool instead of only claiming success."
  },
  g1_trace_contract_judge: {
    zh: "工具与 Trace 规则",
    en: "Tool and trace contract",
    detailZh: "检查必需工具、参数、调用顺序和执行记录。",
    detailEn: "Checks required tools, arguments, ordering, and execution evidence."
  },
  g2_output_contract_judge: {
    zh: "最终回答规则",
    en: "Final answer contract",
    detailZh: "检查最终回答是否满足场景要求。",
    detailEn: "Checks whether the final answer satisfies the scenario contract."
  },
  g3_replay_sandbox_judge: {
    zh: "Trace 可复查性",
    en: "Trace replayability",
    detailZh: "检查执行过程是否完整到足以复查和重放。",
    detailEn: "Checks whether the execution evidence is complete enough to inspect and replay."
  },
  g3_semantic_reference_judge: {
    zh: "语义事实一致性",
    en: "Semantic grounding",
    detailZh: "检查回答中的事实是否和已有证据一致。",
    detailEn: "Checks whether claims in the answer agree with available evidence."
  },
  g3_safety_boundary_judge: {
    zh: "安全边界",
    en: "Safety boundary",
    detailZh: "检查敏感信息、权限和高风险操作是否越界。",
    detailEn: "Checks secrets, permissions, and high-risk operations for policy violations."
  }
};

const rubricLabels: Record<string, { zh: string; en: string }> = {
  task_completion: { zh: "任务完成度", en: "Task completion" },
  skill_protocol: { zh: "工具流程", en: "Tool protocol" },
  argument_fidelity: { zh: "参数准确性", en: "Argument fidelity" },
  safety_permissions: { zh: "安全与权限", en: "Safety and permissions" },
  final_response_quality: { zh: "最终回答质量", en: "Final answer quality" },
  required_tool_execution: { zh: "必需工具执行", en: "Required tool execution" },
  evidence_grounding: { zh: "证据支撑", en: "Evidence grounding" }
};

const failureLabels: Record<string, { zh: string; en: string }> = {
  none: { zh: "无失败", en: "No failure" },
  missing_required_tool: { zh: "缺少必需工具调用", en: "Missing required tool" },
  unnecessary_tool_call: { zh: "调用了不必要的工具", en: "Unnecessary tool call" },
  wrong_intent: { zh: "理解错用户意图", en: "Wrong intent" },
  wrong_tool: { zh: "选择了错误工具", en: "Wrong tool" },
  wrong_argument: { zh: "工具参数错误", en: "Wrong tool argument" },
  unsafe_action: { zh: "不安全操作", en: "Unsafe action" },
  unsupported_claim: { zh: "结论缺少证据", en: "Unsupported claim" }
};

const traceLabels: Record<string, { zh: string; en: string }> = {
  "dialogue.message": { zh: "对话消息", en: "Dialogue message" },
  message: { zh: "对话消息", en: "Message" },
  agent_response: { zh: "Agent 回答", en: "Agent response" },
  "tool.tool_call": { zh: "工具调用", en: "Tool call" },
  tool_call: { zh: "工具调用检查", en: "Tool call check" },
  tool_result: { zh: "工具返回结果", en: "Tool result" }
};

export function judgeLabel(value: unknown, zh: boolean) {
  const id = String(value || "unknown_judge");
  const label = judgeLabels[id];
  return {
    id,
    title: label ? (zh ? label.zh : label.en) : id.replaceAll("_", " "),
    detail: label ? (zh ? label.detailZh : label.detailEn) : (zh ? "查看该评测器的分数、理由和证据。" : "Inspect this judge's score, rationale, and evidence.")
  };
}

export function rubricLabel(value: unknown, zh: boolean) {
  const id = String(value || "unknown_rubric");
  const label = rubricLabels[id];
  return label ? (zh ? label.zh : label.en) : id.replaceAll("_", " ");
}

export function failureClassLabel(value: unknown, zh: boolean) {
  const id = String(value || "none");
  const label = failureLabels[id];
  return label ? (zh ? label.zh : label.en) : id.replaceAll("_", " ");
}

export function traceEventLabel(value: unknown, zh: boolean) {
  const id = String(value || "event");
  const label = traceLabels[id];
  return label ? (zh ? label.zh : label.en) : id.replaceAll(/[._]/g, " ");
}
