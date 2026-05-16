"""Documentation and technical writing agent."""

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


class DocsAgent(ReactAgent):
    """Agent specialized in documentation and docstrings."""

    name = "docs"
    description = "Maintains codebase documentation and inline docstrings."

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
                "You are a technical writer and documentation expert. "
                "Your goal is to keep the project's documentation clear, accurate, and up-to-date. "
                "1. Read the source code to understand recent changes. "
                "2. Update README.md, ARCHITECTURE.md, and other Markdown files. "
                "3. Ensure all public functions and classes have descriptive docstrings. "
                "4. Use file_read, file_write, and file_patch tools to make updates."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )
