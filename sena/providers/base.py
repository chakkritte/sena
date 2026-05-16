"""Shared provider helpers, retry logic, and normalization."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
import tenacity
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from sena.core.models import Message, StreamChunk, ToolCall, ToolCallChunk

logger = structlog.get_logger()


class ProviderError(Exception):
    """Base exception for provider failures."""


class RateLimitError(ProviderError):
    """Provider rate limit exceeded."""


class AuthenticationError(ProviderError):
    """Invalid or missing API key."""


class ModelNotFoundError(ProviderError):
    """Requested model is unavailable."""


RETRY_POLICY = tenacity.retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (ProviderError, asyncio.TimeoutError, ConnectionError)
    ),
)


def _message_to_openai(msg: Message) -> dict[str, Any]:
    """Convert a Sena Message to OpenAI chat completion format."""
    if msg.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id,
            "content": msg.content or "",
        }
    if msg.tool_calls:
        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ],
        }
    return {"role": msg.role, "content": msg.content or ""}


def _message_to_anthropic(msg: Message) -> dict[str, Any]:
    """Convert a Sena Message to Anthropic format."""
    if msg.role == "tool":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content or "",
                }
            ],
        }
    if msg.tool_calls:
        content: list[dict[str, Any]] = []
        if msg.content:
            content.append({"type": "text", "text": msg.content})
        for tc in msg.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                }
            )
        return {"role": "assistant", "content": content}
    return {"role": msg.role, "content": msg.content or ""}


class ToolAccumulator:
    """Accumulates partial tool call chunks across stream tokens.

    Providers like OpenAI emit tool calls across multiple chunks with
    incremental JSON arguments. This class reconstructs complete calls.
    """

    def __init__(self) -> None:
        self._active: dict[int, dict[str, Any]] = {}
        self._emitted_start: set[int] = set()

    def ingest(self, tool_call_chunks: list[Any]) -> list[StreamChunk]:
        """Process raw provider tool call chunks and emit Sena StreamChunks."""
        chunks: list[StreamChunk] = []
        for tc in tool_call_chunks:
            idx = getattr(tc, "index", 0)
            if idx not in self._active:
                self._active[idx] = {"id": "", "name": "", "arguments": ""}
            state = self._active[idx]
            if getattr(tc, "id", None):
                state["id"] = tc.id
            if getattr(tc, "function", None):
                fn = tc.function
                if getattr(fn, "name", None):
                    state["name"] = fn.name
                if getattr(fn, "arguments", None):
                    state["arguments"] += fn.arguments
            # Emit start when we have a name
            if state["name"] and idx not in self._emitted_start:
                self._emitted_start.add(idx)
                chunks.append(
                    StreamChunk(
                        tool_call=ToolCallChunk(
                            id=state["id"],
                            name=state["name"],
                            is_start=True,
                        )
                    )
                )
            # Emit argument delta
            if getattr(tc, "function", None) and getattr(tc.function, "arguments", None):
                chunks.append(
                    StreamChunk(
                        tool_call=ToolCallChunk(
                            id=state["id"],
                            arguments_delta=tc.function.arguments,
                        )
                    )
                )
        return chunks

    def flush(self) -> list[ToolCall]:
        """Return completed tool calls and reset state."""
        calls: list[ToolCall] = []
        for state in self._active.values():
            try:
                args = json.loads(state["arguments"]) if state["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            calls.append(
                ToolCall(
                    id=state["id"],
                    name=state["name"],
                    arguments=args,
                )
            )
        self._active.clear()
        self._emitted_start.clear()
        return calls
