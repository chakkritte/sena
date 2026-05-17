"""Base classes for providers, tools, memory, and agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from carbonclaw.core.models import (
    CompletionRequest,
    CompletionResponse,
    MemoryEntry,
    ProviderInfo,
    StreamChunk,
    ToolDefinition,
    ToolResult,
)

ApprovalCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class BaseProvider(ABC):
    """Abstract LLM provider adapter.

    Each adapter normalizes a vendor-specific SDK into the CarbonClaw
    unified completion and streaming interface.
    """

    info: ProviderInfo

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Non-streaming chat completion."""

    @abstractmethod
    def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion.

        Yields StreamChunk objects with partial content / tool call updates.
        The final chunk contains finish_reason and usage.
        """

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return available model IDs."""

    async def health(self) -> bool:
        """Check provider connectivity."""
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False


class BaseTool(ABC):
    """Abstract tool callable by agents and chat."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] | None = None
    requires_approval: bool = False

    @property
    def definition(self) -> ToolDefinition:
        if self.input_schema is None:
            return ToolDefinition(
                name=self.name,
                description=self.description,
                parameters={"type": "object", "properties": {}},
            )
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_schema,
        )

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with parsed arguments."""


class BaseMemory(ABC):
    """Abstract memory backend."""

    @abstractmethod
    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a memory entry and return its ID."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories by semantic or keyword match."""

    @abstractmethod
    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Fetch a specific memory entry by ID."""

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry. Returns True if deleted."""

    @abstractmethod
    async def namespaces(self) -> list[str]:
        """List available namespaces."""


class BaseAgent(ABC):
    """Abstract agent with planning and execution hooks."""

    name: str = ""
    description: str = ""

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.approval_callback = approval_callback
        self._tool_map = {t.name: t for t in tools}

    @abstractmethod
    async def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        """Execute the agent on a task and return the final result."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Dispatch a tool call by name with safety checks and error handling."""
        from carbonclaw.telemetry.otel import trace_span
        
        with trace_span(f"agent.tool.{name}", attributes={"tool": name}):
            tool = self._tool_map.get(name)
            if tool is None:
                logger.error("agent.tool_not_found", tool=name)
                return ToolResult(
                    tool_call_id="",
                    name=name,
                    content=f"Error: Tool '{name}' not found. Available: {', '.join(self._tool_map.keys())}",
                    is_error=True,
                )

            # Human-in-the-loop validation
            if tool.requires_approval and self.approval_callback:
                try:
                    approved = await self.approval_callback(name, arguments)
                    if not approved:
                        logger.info("agent.tool_denied", tool=name)
                        return ToolResult(
                            tool_call_id="",
                            name=name,
                            content="Action denied by user.",
                            is_error=True,
                        )
                except Exception as e:
                    logger.exception("agent.approval_callback_error", tool=name)
                    return ToolResult(
                        tool_call_id="",
                        name=name,
                        content=f"Error during human approval process: {str(e)}",
                        is_error=True,
                    )

            # Execution with isolation and crash protection
            try:
                logger.info("agent.tool_executing", tool=name)
                result = await tool.execute(arguments)
                return result
            except Exception as e:
                logger.exception("agent.tool_execution_failed", tool=name)
                return ToolResult(
                    tool_call_id="",
                    name=name,
                    content=f"Unexpected error during '{name}' execution: {str(e)}",
                    is_error=True,
                )
