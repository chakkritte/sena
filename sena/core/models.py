"""Shared Pydantic models for messages, tools, streaming, and providers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCallChunk(BaseModel):
    """A fragment of a streaming tool call."""

    id: str | None = None
    name: str | None = None
    arguments_delta: str | None = None
    is_start: bool = False
    is_end: bool = False


class StreamChunk(BaseModel):
    """A unified chunk emitted by any provider during streaming."""

    content: str | None = None
    tool_call: ToolCallChunk | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


class ToolCall(BaseModel):
    """A resolved tool call from a model response."""

    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    """A chat message in the unified Sena format.

    Providers convert to/from their native formats.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None  # tool name for tool result messages


class ToolDefinition(BaseModel):
    """A tool definition in OpenAI-compatible JSON Schema format."""

    type: Literal["function"] = "function"
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the tool's input",
    )
    strict: bool | None = None

    def to_openai(self) -> dict[str, Any]:
        """Return OpenAI tool format."""
        return {
            "type": self.type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                **({"strict": self.strict} if self.strict is not None else {}),
            },
        }

    def to_anthropic(self) -> dict[str, Any]:
        """Return Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolResult(BaseModel):
    """The result of executing a tool."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


class AgentState(BaseModel):
    """Snapshot of agent execution state."""

    status: Literal["idle", "running", "waiting", "error", "done"] = "idle"
    current_task: str | None = None
    messages: list[Message] = Field(default_factory=list)
    memory_context: str | None = None


class MemoryEntry(BaseModel):
    """A single memory record."""

    id: str | None = None
    namespace: str = "default"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    score: float | None = None  # relevance score for retrieval


class ProviderInfo(BaseModel):
    """Metadata about a provider."""

    name: str
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_embeddings: bool = False
    default_model: str | None = None
    requires_api_key: bool = True
    base_url: str | None = None


class CompletionRequest(BaseModel):
    """Normalized completion request."""

    messages: list[Message]
    model: str
    tools: list[ToolDefinition] = Field(default_factory=list)
    temperature: float | None = 0.7
    max_tokens: int | None = None
    system: str | None = None
    stream: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    """Normalized completion response (non-streaming)."""

    message: Message
    usage: Usage | None = None
    model: str | None = None
    provider: str | None = None
    raw: dict[str, Any] | None = None
