"""Tool registry and schema helpers."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, create_model

from sena.core.base import BaseTool
from sena.core.models import ToolDefinition, ToolResult


def _pydantic_model_from_function(func: Any) -> type[BaseModel]:
    """Generate a Pydantic model from a function signature for JSON Schema."""
    sig = inspect.signature(func)
    fields: dict[str, tuple[type, Any]] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else Any
        default = param.default if param.default != inspect.Parameter.empty else ...
        fields[name] = (annotation, default)
    return create_model(f"{func.__name__}_input", **fields)  # type: ignore[call-overload,no-any-return]


class ToolRegistry:
    """Central registry for tool discovery and dispatch."""

    # Tools whose results can be safely cached within a session
    _CACHEABLE_TOOLS = frozenset(["file_read", "git", "shell"])

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._cache: dict[str, ToolResult] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def _cache_key(self, name: str, arguments: dict[str, Any]) -> str:
        import hashlib
        import json

        payload = json.dumps(arguments, sort_keys=True, default=str)
        return f"{name}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_call_id="",
                name=name,
                content=f"Tool '{name}' is not available.",
                is_error=True,
            )

        # Cache deterministic read-only tools
        if name in self._CACHEABLE_TOOLS:
            key = self._cache_key(name, arguments)
            if key in self._cache:
                cached = self._cache[key]
                # Return a copy so callers can't mutate shared state
                return ToolResult(
                    tool_call_id=cached.tool_call_id,
                    name=cached.name,
                    content=cached.content,
                    is_error=cached.is_error,
                )
            result = await tool.execute(arguments)
            if not result.is_error:
                self._cache[key] = result
            return result

        return await tool.execute(arguments)

    def clear_cache(self) -> None:
        """Clear the tool result cache."""
        self._cache.clear()
