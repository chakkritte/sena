"""Agent base with ReAct execution loop."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from carbonclaw.core.base import ApprovalCallback, BaseAgent, BaseMemory, BaseProvider, BaseTool
from carbonclaw.core.models import (
    CompletionRequest,
    Message,
    StreamChunk,
    ToolCall,
)
from carbonclaw.tools.base import ToolRegistry

logger = structlog.get_logger()

__all__ = ["AgentContext", "ReactAgent"]


class AgentContext:
    """Mutable context shared across agent steps."""

    def __init__(
        self,
        provider: BaseProvider,
        tools: ToolRegistry,
        memory: BaseMemory,
        system_prompt: str = "",
        model: str | None = None,
        max_iterations: int = 20,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.system_prompt = system_prompt
        self.model = model
        self.max_iterations = max_iterations
        self.messages: list[Message] = []
        if system_prompt:
            self.messages.append(Message(role="system", content=system_prompt))


class ReactAgent(BaseAgent):
    """ReAct-style agent that reasons and acts via tool calls."""

    name = "react"
    description = "General-purpose reasoning agent with tool use."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        system_prompt: str = (
            "You are CarbonClaw, an AI software engineering assistant. "
            "You have access to tools for file operations, shell execution, and git. "
            "Think step by step, then use tools when needed."
        ),
        model: str | None = None,
        max_iterations: int = 20,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            approval_callback=approval_callback,
        )
        self.system_prompt = system_prompt
        self.model = model
        self.max_iterations = max_iterations

    async def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        from carbonclaw.telemetry.otel import trace_span
        from carbonclaw.config.settings import CarbonClawConfig
        from carbonclaw.context.instructions import InstructionTierManager
        from carbonclaw.telemetry.carbon import track_carbon, get_greener_recommendation

        # Load dynamic context
        config = CarbonClawConfig()
        itm = InstructionTierManager()
        instruction_context = itm.aggregate()

        # Simple complexity estimation (based on task length and common keywords)
        complexity = 0.5
        if len(task) < 50:
            complexity -= 0.2
        if any(kw in task.lower() for kw in ["explain", "what is", "simple", "hello"]):
            complexity -= 0.1
        
        recommendation = get_greener_recommendation(task, complexity)
        
        persona_str = ""
        if config.persona:
            persona_str = "\n\nYOUR PERSONA AND PREFERENCES:\n" + "\n".join(
                f"- {k.capitalize()}: {v}" for k, v in config.persona.items()
            )

        learned_rules = await self.memory.retrieve("", namespace="learned_rules", limit=50)
        rules_str = ""
        if learned_rules:
            rules_str = "\n\nLEARNED RULES FROM PAST INTERACTIONS:\n" + "\n".join(
                f"- {r.content}" for r in learned_rules
            )

        system_base = self.system_prompt or ""
        full_system_prompt = system_base + persona_str + rules_str
        if instruction_context:
            full_system_prompt += "\n\nWORKSPACE CONTEXT & INSTRUCTIONS:\n" + instruction_context

        with track_carbon(f"agent.{self.name}", enabled=config.carbon_tracking_enabled) as ct:
            with trace_span(f"agent.{self.name}.run", attributes={"task": task[:100]}):
                ctx = AgentContext(
                    provider=self.provider,
                    tools=ToolRegistry(),
                    memory=self.memory,
                    system_prompt=full_system_prompt,
                    model=self.model,
                    max_iterations=self.max_iterations,
                )
                for t in self.tools:
                    ctx.tools.register(t)
                
                # Auto-register LearnRuleTool for all agents
                from carbonclaw.agents.evolution import LearnRuleTool
                ctx.tools.register(LearnRuleTool(self.memory))

                ctx.messages.append(Message(role="user", content=task))

                for _ in range(ctx.max_iterations):
                    response_chunks: list[StreamChunk] = []
                    with trace_span(
                        f"provider.{self.provider.__class__.__name__}.stream",
                        attributes={"model": ctx.model or ""},
                    ) as span:
                        async for chunk in self.provider.stream(
                            CompletionRequest(
                                messages=ctx.messages,
                                model=ctx.model or "",
                                tools=ctx.tools.definitions(),
                            )
                        ):
                            response_chunks.append(chunk)
                            if chunk.usage:
                                span.set_attribute("usage.prompt_tokens", chunk.usage.prompt_tokens)
                                span.set_attribute("usage.completion_tokens", chunk.usage.completion_tokens)
                                span.set_attribute("usage.total_tokens", chunk.usage.total_tokens)

                    # Accumulate response
                    content_parts: list[str] = []
                    tool_calls: list[ToolCall] = []
                    current_tool: dict[str, Any] | None = None
                    finish_reason: str | None = None

                    for chunk in response_chunks:
                        if chunk.content:
                            content_parts.append(chunk.content)
                        if chunk.tool_call:
                            tc = chunk.tool_call
                            if tc.is_start:
                                current_tool = {
                                    "id": tc.id or "",
                                    "name": tc.name or "",
                                    "arguments": "",
                                }
                            elif tc.arguments_delta:
                                if current_tool is not None:
                                    current_tool["arguments"] += tc.arguments_delta
                            elif tc.is_end:
                                if current_tool is not None:
                                    try:
                                        args = json.loads(current_tool["arguments"])
                                    except json.JSONDecodeError:
                                        args = {}
                                    tool_calls.append(
                                        ToolCall(
                                            id=current_tool["id"],
                                            name=current_tool["name"],
                                            arguments=args,
                                        )
                                    )
                                    current_tool = None
                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason

                    # Handle any dangling tool call
                    if current_tool is not None:
                        try:
                            args = json.loads(current_tool["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append(
                            ToolCall(
                                id=current_tool["id"],
                                name=current_tool["name"],
                                arguments=args,
                            )
                        )

                    assistant_msg = Message(
                        role="assistant",
                        content="".join(content_parts) if content_parts else None,
                        tool_calls=tool_calls or None,
                    )
                    ctx.messages.append(assistant_msg)

                    if not tool_calls:
                        # No tool calls — we're done
                        res = assistant_msg.content or ""
                        if recommendation:
                            res = f"{recommendation}\n\n{res}"
                        return res

                    # Execute tools
                    for call in tool_calls:
                        result = await ctx.tools.execute(call.name, call.arguments)
                        ctx.messages.append(
                            Message(
                                role="tool",
                                content=result.content,
                                tool_call_id=call.id,
                                name=call.name,
                            )
                        )

                # Max iterations reached
                res = ctx.messages[-1].content or "Reached maximum iterations."
                if recommendation:
                    res = f"{recommendation}\n\n{res}"
                return res

    async def stream_run(
        self, task: str, context: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        """Stream the agent's reasoning and tool results as text."""
        from carbonclaw.context.instructions import InstructionTierManager
        from carbonclaw.telemetry.carbon import track_carbon, get_greener_recommendation
        from carbonclaw.config.settings import CarbonClawConfig

        config = CarbonClawConfig()
        itm = InstructionTierManager()
        instruction_context = itm.aggregate()
        
        # Simple complexity estimation
        complexity = 0.5
        if len(task) < 50:
            complexity -= 0.2
        if any(kw in task.lower() for kw in ["explain", "what is", "simple", "hello"]):
            complexity -= 0.1
        
        recommendation = get_greener_recommendation(task, complexity)
        if recommendation:
            yield f"{recommendation}\n\n"

        full_system_prompt = self.system_prompt
        if instruction_context:
            full_system_prompt += "\n\nWORKSPACE CONTEXT & INSTRUCTIONS:\n" + instruction_context

        with track_carbon(f"agent.{self.name}", enabled=config.carbon_tracking_enabled) as ct:
            ctx = AgentContext(
                provider=self.provider,
                tools=ToolRegistry(),
                memory=self.memory,
                system_prompt=full_system_prompt,
                model=self.model,
                max_iterations=self.max_iterations,
            )
            for t in self.tools:
                ctx.tools.register(t)
            ctx.messages.append(Message(role="user", content=task))

            for _ in range(ctx.max_iterations):
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []
                current_tool: dict[str, Any] | None = None
                finish_reason: str | None = None

                async for chunk in self.provider.stream(
                    CompletionRequest(
                        messages=ctx.messages,
                        model=ctx.model or "",
                        tools=ctx.tools.definitions(),
                    )
                ):
                    if chunk.content:
                        content_parts.append(chunk.content)
                        yield chunk.content
                    if chunk.tool_call:
                        tc = chunk.tool_call
                        if tc.is_start:
                            current_tool = {
                                "id": tc.id or "",
                                "name": tc.name or "",
                                "arguments": "",
                            }
                        elif tc.arguments_delta:
                            if current_tool is not None:
                                current_tool["arguments"] += tc.arguments_delta
                        elif tc.is_end:
                            if current_tool is not None:
                                try:
                                    args = json.loads(current_tool["arguments"])
                                except json.JSONDecodeError:
                                    args = {}
                                tool_calls.append(
                                    ToolCall(
                                        id=current_tool["id"],
                                        name=current_tool["name"],
                                        arguments=args,
                                    )
                                )
                                current_tool = None
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason

                if current_tool is not None:
                    try:
                        args = json.loads(current_tool["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(
                        ToolCall(
                            id=current_tool["id"],
                            name=current_tool["name"],
                            arguments=args,
                        )
                    )

                assistant_msg = Message(
                    role="assistant",
                    content="".join(content_parts) if content_parts else None,
                    tool_calls=tool_calls or None,
                )
                ctx.messages.append(assistant_msg)

                if not tool_calls:
                    if config.carbon_tracking_enabled:
                        emissions = ct.last_emissions
                        yield f"\n\n[Carbon Emissions: {emissions:.6f} kg CO2]"
                    return

                for call in tool_calls:
                    result = await ctx.tools.execute(call.name, call.arguments)
                    ctx.messages.append(
                        Message(
                            role="tool",
                            content=result.content,
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                    yield f"\n\n[{call.name}]\n{result.content}\n\n"

            yield "\n[Reached maximum iterations]\n"
            if config.carbon_tracking_enabled:
                emissions = ct.last_emissions
                yield f"\n\n[Carbon Emissions: {emissions:.6f} kg CO2]"
