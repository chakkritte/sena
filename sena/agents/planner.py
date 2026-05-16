"""Planner agent for task decomposition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sena.agents.base import ReactAgent

if TYPE_CHECKING:
    from sena.core.base import (
        ApprovalCallback,
        BaseMemory,
        BaseProvider,
        BaseTool,
    )


class PlannerAgent(ReactAgent):
    """Agent that breaks down high-level tasks into executable steps."""

    name = "planner"
    description = "Decomposes tasks into step-by-step plans with milestones."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
        max_iterations: int = 5,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            system_prompt=(
                "You are a technical project planner. "
                "Break the user's request into clear, actionable steps. "
                "Each step should be specific and verifiable. "
                "Use git and file_read tools to understand the codebase before planning."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )
