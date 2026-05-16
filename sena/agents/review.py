"""Review agent for code review and quality assurance."""

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


class ReviewAgent(ReactAgent):
    """Agent that reviews code for correctness, style, and security."""

    name = "review"
    description = "Reviews code changes and provides structured feedback."

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
                "You are a senior code reviewer. "
                "Review the provided code for correctness, performance, security, and style. "
                "Be constructive and specific. Use file_read and git tools to inspect the codebase."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )
