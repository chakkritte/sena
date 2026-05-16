"""Supervisor agent that orchestrates multiple agents via event bus."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from sena.agents.base import ReactAgent
from sena.agents.coding import CodingAgent
from sena.agents.docs import DocsAgent
from sena.agents.planner import PlannerAgent
from sena.agents.qa import QAAgent
from sena.agents.review import ReviewAgent
from sena.core.base import (
    ApprovalCallback,
    BaseMemory,
    BaseProvider,
    BaseTool,
)
from sena.core.events import Event, EventBus
from sena.core.models import Message
from sena.memory.sqlite import SQLiteMemory
from sena.providers.registry import ProviderRegistry
from sena.tools.base import ToolRegistry
from sena.tools.browser import BrowserTool
from sena.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from sena.tools.git import GitTool
from sena.tools.shell import ShellTool

logger = structlog.get_logger()


class SupervisorAgent:
    """Coordinates Planner, Coding, and Review agents using the event bus.

    Delegates tasks to the most appropriate agent, monitors progress,
    and routes results back to the caller.
    """

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.model = model
        self.approval_callback = approval_callback
        self.bus = EventBus()
        self._agents: dict[str, ReactAgent] = {}
        self._running: dict[str, asyncio.Task[Any]] = {}

        # Register agents
        self._agents["planner"] = PlannerAgent(provider, tools, memory, model, approval_callback=approval_callback)
        self._agents["coding"] = CodingAgent(provider, tools, memory, model, approval_callback=approval_callback)
        self._agents["review"] = ReviewAgent(provider, tools, memory, model, approval_callback=approval_callback)
        self._agents["qa"] = QAAgent(provider, tools, memory, model, approval_callback=approval_callback)
        self._agents["docs"] = DocsAgent(provider, tools, memory, model, approval_callback=approval_callback)

    async def delegate(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Delegate a task to a named agent and return the result."""
        from sena.telemetry.otel import trace_span

        with trace_span("supervisor.delegate", attributes={"agent": agent_name}):
            agent = self._agents.get(agent_name)
            if agent is None:
                raise ValueError(f"Unknown agent: {agent_name}")

            event = Event(
                type="task.delegated",
                payload={"agent": agent_name, "task": task, "context": context},
                source="supervisor",
                target=agent_name,
            )
            await self.bus.publish(event)

            result = await agent.run(task, context)

            await self.bus.publish(
                Event(
                    type="task.completed",
                    payload={"agent": agent_name, "result": result},
                    source=agent_name,
                    target="supervisor",
                )
            )

            await self.memory.store(
                f"[{agent_name}] {task} -> {result[:200]}",
                namespace="orchestration",
                metadata={"agent": agent_name, "task": task},
            )

            return result

    async def stream_delegate(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a delegated agent's output."""
        agent = self._agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        await self.bus.publish(
            Event(
                type="task.delegated",
                payload={"agent": agent_name, "task": task},
                source="supervisor",
                target=agent_name,
            )
        )

        async for chunk in agent.stream_run(task, context):
            yield chunk

        await self.bus.publish(
            Event(
                type="task.completed",
                payload={"agent": agent_name},
                source=agent_name,
                target="supervisor",
            )
        )

    async def run_workflow(
        self,
        task: str,
        auto_plan: bool = True,
        auto_review: bool = True,
    ) -> str:
        """Execute a full workflow: plan -> code -> review."""
        from sena.telemetry.otel import trace_span

        with trace_span("supervisor.workflow", attributes={"task": task[:100]}):
            logger.info("supervisor.workflow.start", task=task[:80])

            # Step 1: Plan
            if auto_plan:
                plan = await self.delegate("planner", f"Plan: {task}")
                logger.info("supervisor.plan.complete", plan_length=len(plan))
            else:
                plan = task

            # Step 2: Code
            code_result = await self.delegate("coding", plan)
            logger.info("supervisor.code.complete", result_length=len(code_result))

            # Step 3: Review
            if auto_review:
                review = await self.delegate("review", f"Review the following changes:\n\n{code_result}")
                logger.info("supervisor.review.complete", review_length=len(review))
                return f"## Plan\n{plan}\n\n## Implementation\n{code_result}\n\n## Review\n{review}"

            return f"## Plan\n{plan}\n\n## Implementation\n{code_result}"

    async def stream_workflow(
        self,
        task: str,
        auto_plan: bool = True,
        auto_review: bool = True,
    ) -> AsyncIterator[str]:
        """Stream a full workflow with labeled sections."""
        yield "# Planning\n\n"
        if auto_plan:
            async for chunk in self.stream_delegate("planner", f"Plan: {task}"):
                yield chunk
            yield "\n\n"

        yield "# Implementation\n\n"
        async for chunk in self.stream_delegate("coding", task):
            yield chunk
        yield "\n\n"

        if auto_review:
            yield "# Review\n\n"
            async for chunk in self.stream_delegate("review", f"Review: {task}"):
                yield chunk
            yield "\n"

    @classmethod
    async def create_default(cls, provider_name: str | None = None) -> SupervisorAgent:
        """Factory: build a SupervisorAgent from SenaConfig with all default tools."""
        from sena.config.settings import SenaConfig

        config = SenaConfig()
        name = provider_name or config.default_provider
        model = config.default_model or "llama3.2"
        provider = ProviderRegistry.create(name, config)
        memory = SQLiteMemory()

        tools = ToolRegistry()
        tools.register(ShellTool())
        tools.register(BrowserTool())
        tools.register(FileReadTool())
        tools.register(FileWriteTool())
        tools.register(FilePatchTool())
        tools.register(GitTool())

        return cls(provider, tools.list_tools(), memory, model)
