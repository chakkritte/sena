"""Agent base with ReAct execution loop."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from sena.core.base import ApprovalCallback, BaseAgent, BaseMemory, BaseProvider, BaseTool
from sena.core.models import (
    CompletionRequest,
    Message,
    StreamChunk,
    ToolCall,
)
from sena.tools.base import ToolRegistry

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
        max_iterations: int = 10,
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
            "You are Sena, an AI software engineering assistant. "
            "You have access to tools for file operations, shell execution, and git. "
            "Think step by step, then use tools when needed."
        ),
        model: str | None = None,
        max_iterations: int = 10,
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
        from sena.telemetry.otel import trace_span

        with trace_span(f"agent.{self.name}.run", attributes={"task": task[:100]}):
            ctx = AgentContext(
                provider=self.provider,
                tools=ToolRegistry(),
                memory=self.memory,
                system_prompt=self.system_prompt,
                model=self.model,
                max_iterations=self.max_iterations,
            )
            for t in self.tools:
                ctx.tools.register(t)

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
                    return assistant_msg.content or ""

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
            return ctx.messages[-1].content or "Reached maximum iterations."

    async def stream_run(
        self, task: str, context: dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        """Stream the agent's reasoning and tool results as text."""
        ctx = AgentContext(
            provider=self.provider,
            tools=ToolRegistry(),
            memory=self.memory,
            system_prompt=self.system_prompt,
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
