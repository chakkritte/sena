"""Tool for entering planning mode."""

from __future__ import annotations

from typing import Any, Optional

from sena.core.base import BaseTool, ToolResult


class EnterPlanModeTool(BaseTool):
    """Enters a safe planning mode to research and design complex changes."""

    name = "enter_plan_mode"
    description = (
        "Enters a safe planning mode to research and design complex changes. "
        "Use this for tasks that are ambiguous, broad in scope, or involve "
        "architectural decisions. Do NOT use this for straightforward bug fixes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Short reason explaining why you are entering plan mode.",
            },
        },
        "required": ["reason"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        reason = kwargs["reason"]
        # In a real CLI, this might change the UI state.
        # For now, we return a instruction block that guides the agent.
        return ToolResult(
            tool_call_id="",
            name=self.name,
            content=(
                f"### PLANNING MODE ENABLED\n"
                f"Reason: {reason}\n\n"
                "You are now in Planning Mode. Your goal is to research and design. "
                "1. DO NOT make any changes to the codebase yet.\n"
                "2. Use search and read tools to understand the current state.\n"
                "3. Draft a comprehensive design document or strategy.\n"
                "4. Present the plan to the user for approval before proceeding to Execution."
            )
        )
