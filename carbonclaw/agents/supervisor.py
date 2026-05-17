"""Supervisor agent that orchestrates multiple agents via event bus."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from carbonclaw.agents.base import ReactAgent
from carbonclaw.agents.coding import CodingAgent
from carbonclaw.agents.docs import DocsAgent
from carbonclaw.agents.planner import PlannerAgent
from carbonclaw.agents.qa import QAAgent
from carbonclaw.agents.review import ReviewAgent
from carbonclaw.core.base import (
    ApprovalCallback,
    BaseMemory,
    BaseProvider,
    BaseTool,
)
from carbonclaw.core.events import Event, EventBus
from carbonclaw.core.models import Message
from carbonclaw.memory.sqlite import SQLiteMemory
from carbonclaw.providers.registry import ProviderRegistry
from carbonclaw.tools.base import ToolRegistry
from carbonclaw.tools.browser import BrowserTool
from carbonclaw.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from carbonclaw.tools.git import GitTool
from carbonclaw.tools.shell import ShellTool

logger = structlog.get_logger()


from carbonclaw.agents.research import ResearchAgent
from carbonclaw.tools.nodejs import RunNodeJSTool
from carbonclaw.prompts.pptxgenjs_context import PPTXGENJS_SYSTEM_CONTEXT
from carbonclaw.core.models import TaskType


class SupervisorAgent:
    """Coordinates Specialized agents using the event bus.

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
        from carbonclaw.config.settings import CarbonClawConfig
        
        self.provider = provider
        self.tools = tools + [RunNodeJSTool()] # Ensure Node.js is available
        self.memory = memory
        self.model = model
        self.approval_callback = approval_callback
        self.bus = EventBus()
        self._agents: dict[str, ReactAgent] = {}
        self._running: dict[str, asyncio.Task[Any]] = {}
        
        config = CarbonClawConfig()
        overrides = config.agent_overrides

        # Helper to create agent with optional override
        def create_agent(cls: type[ReactAgent], name: str, system_ext: str = "") -> ReactAgent:
            target_model = overrides.get(name, "auto")
            
            use_model = model
            if target_model != "auto" and target_model is not None:
                use_model = target_model
                
            agent = cls(
                provider, 
                self.tools, 
                memory, 
                use_model, 
                approval_callback=approval_callback
            )
            if system_ext:
                agent.system_prompt += "\n\n" + system_ext
            return agent

        # Register agents
        self._agents["planner"] = create_agent(PlannerAgent, "planner")
        self._agents["coding"] = create_agent(CodingAgent, "coding")
        self._agents["review"] = create_agent(ReviewAgent, "review")
        self._agents["qa"] = create_agent(QAAgent, "qa")
        self._agents["docs"] = create_agent(DocsAgent, "docs")
        self._agents["research"] = create_agent(ResearchAgent, "research")

    async def run(self, task: str) -> str:
        """Main entry point: classify and execute."""
        from carbonclaw.routing.classifier import classify_task
        task_type = classify_task(task)
        
        logger.info("supervisor.task_classified", type=task_type.value)

        # Special handling for Research
        if task_type == TaskType.RESEARCH:
            agent = self._agents["research"]
            if isinstance(agent, ResearchAgent):
                result = await agent.research(task)
                return result.report

        # Special handling for Slides
        if task_type == TaskType.SLIDES:
            # Re-init coding agent with extra context
            self._agents["coding"].system_prompt += "\n\n" + PPTXGENJS_SYSTEM_CONTEXT

        # Default multi-agent pipeline (Plan -> Code -> Review)
        return await self._orchestrate_pipeline(task)

    async def delegate(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Delegate a task to a named agent and return the result."""
        from carbonclaw.telemetry.otel import trace_span

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
        from carbonclaw.telemetry.otel import trace_span

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
            review = ""
            if auto_review:
                review = await self.delegate("review", f"Review the following changes:\n\n{code_result}")
                logger.info("supervisor.review.complete", review_length=len(review))
            
            # Step 4: Self-Evolution (Reflection)
            try:
                from carbonclaw.agents.evolution import EvolutionAgent
                evo = EvolutionAgent(self.provider, self.tools, self.memory, self.model)
                # Combine messages for reflection
                history = [
                    Message(role="user", content=task),
                    Message(role="assistant", content=f"Implementation: {code_result}"),
                ]
                if review:
                    history.append(Message(role="assistant", content=f"Review: {review}"))
                
                await evo.reflect(history)
                logger.info("supervisor.evolution.complete")
            except Exception as e:
                logger.warning("supervisor.evolution.failed", error=str(e))

            if auto_review:
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
        """Factory: build a SupervisorAgent from CarbonClawConfig with all default tools."""
        from carbonclaw.config.settings import CarbonClawConfig

        config = CarbonClawConfig()
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
