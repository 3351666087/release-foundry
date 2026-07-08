export class RespondingMockAgent {
  reset() {
    return true;
  }

  respond(message) {
    const text = typeof message === "string" ? message : message?.text ?? "";
    if (/\d/.test(text) && text.includes("+")) {
      const expression = extractExpression(text);
      const value = evaluateExpression(expression);
      return {
        text: `The answer is ${formatNumber(value)}.`,
        tool_calls: [{ name: "calculator", arguments: { expression }, output: { value } }],
        status: "ok",
        metadata: { local_only: true, implementation: "examples/agents/mock_agent_ts.mjs" },
      };
    }
    return {
      text: `Echo: ${text}`,
      tool_calls: text.includes("tool")
        ? [{ name: "mock_tool", arguments: { query: text }, output: { ok: true } }]
        : [],
      status: "ok",
      metadata: { local_only: true, implementation: "examples/agents/mock_agent_ts.mjs" },
    };
  }
}

export default RespondingMockAgent;

function extractExpression(text) {
  const matches = [...text.matchAll(/[-+*/()\d\s.]+/g)]
    .map((match) => match[0].trim())
    .filter((value) => /\d/.test(value));
  if (!matches.length) {
    throw new Error("no arithmetic expression found");
  }
  return matches.sort((left, right) => right.length - left.length)[0];
}

function evaluateExpression(expression) {
  if (!/^[-+*/().\d\s]+$/.test(expression)) {
    throw new Error("expression must contain only numbers and arithmetic operators");
  }
  const value = Function(`"use strict"; return (${expression});`)();
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error("expression did not evaluate to a finite number");
  }
  return value;
}

function formatNumber(value) {
  return Number.isInteger(value) ? String(value) : String(value);
}
