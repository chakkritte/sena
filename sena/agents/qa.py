"""QA and Test Engineering agent."""

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


class QAAgent(ReactAgent):
    """Agent specialized in writing and running tests."""

    name = "qa"
    description = "Generates and executes tests to verify code changes."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
        max_iterations: int = 10,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            system_prompt=(
                "You are an expert QA Engineer. Your goal is to ensure code quality through testing. "
                "1. Read the source code to understand its functionality. "
                "2. Write robust test cases using pytest. "
                "3. Execute the tests using the shell or python interpreter tools. "
                "4. If tests fail, analyze the output and fix either the tests or the source code. "
                "5. Repeat until all tests pass."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )
