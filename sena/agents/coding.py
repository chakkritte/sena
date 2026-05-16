"""Coding agent specialized for software engineering tasks."""

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


class CodingAgent(ReactAgent):
    """Agent focused on code reading, editing, and shell execution."""

    name = "coding"
    description = "Writes, edits, and reviews code using file and shell tools."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
        max_iterations: int = 15,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            system_prompt=(
                "You are a senior software engineer. "
                "You have access to tools: file_read, file_write, file_patch, shell, git. "
                "Follow best practices: read files before editing, use patches for small changes, "
                "write files for new code. Always check git status before making changes. "
                "Explain your reasoning briefly, then act."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )
