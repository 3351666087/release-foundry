from __future__ import annotations

from typing import Any


class EvalRunner:
    """Minimal text-only runner shape for static compatibility inspection."""

    def run_action(self, agent: Any, action: dict[str, Any]) -> Any:
        content = action.get("content", "")
        return agent.respond(content)
