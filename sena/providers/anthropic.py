"""Anthropic Claude provider adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from anthropic._exceptions import APIConnectionError, APIStatusError
from anthropic._exceptions import AuthenticationError as AnthropicAuthError
from anthropic._exceptions import RateLimitError as AnthropicRateLimitError

from sena.core.base import BaseProvider
from sena.core.models import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderInfo,
    StreamChunk,
    ToolCallChunk,
    Usage,
)
from sena.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
    _message_to_anthropic,
)

logger = structlog.get_logger()


class AnthropicProvider(BaseProvider):
    """Provider adapter for Anthropic Claude."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        self.client = AsyncAnthropic(api_key=api_key, base_url=base_url)
        self.default_model = default_model
        self.info = ProviderInfo(
            name="anthropic",
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_embeddings=False,
            default_model=default_model,
            requires_api_key=True,
            base_url=base_url or "https://api.anthropic.com",
        )
        self._current_tool: dict[str, Any] | None = None

    @staticmethod
    def _extract_system(messages: list[Message]) -> tuple[str | None, list[Message]]:
        system_msg = next((m for m in messages if m.role == "system"), None)
        rest = [m for m in messages if m.role != "system"]
        return system_msg.content if system_msg else None, rest

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        system, msgs = self._extract_system(request.messages)
        native = [_message_to_anthropic(m) for m in msgs]
        tools = [t.to_anthropic() for t in request.tools] if request.tools else None
        try:
            response = await self.client.messages.create(
                model=request.model or self.default_model,
                max_tokens=request.max_tokens or 4096,
                messages=native,  # type: ignore[arg-type]
                system=system or "",
                tools=tools,  # type: ignore[arg-type]
                temperature=request.temperature or 1.0,
                stream=False,
                **request.extra,
            )
            content_text = ""
            tool_calls: list[Any] = []
            for block in getattr(response, "content", []):
                if block.type == "text":
                    content_text += getattr(block, "text", "")
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                            "arguments": getattr(block, "input", {}),
                        }
                    )
            message = Message(
                role="assistant",
                content=content_text or None,
                tool_calls=tool_calls or None,
            )
            usage = getattr(response, "usage", None)
            usage_input = getattr(usage, "input_tokens", 0) if usage else 0
            usage_output = getattr(usage, "output_tokens", 0) if usage else 0
            usage = Usage(
                prompt_tokens=usage_input,
                completion_tokens=usage_output,
                total_tokens=usage_input + usage_output,
            )
            return CompletionResponse(
                message=message,
                usage=usage,
                model=getattr(response, "model", self.default_model),
                provider="anthropic",
            )
        except AnthropicAuthError as e:
            raise AuthenticationError(str(e)) from e
        except AnthropicRateLimitError as e:
            raise RateLimitError(str(e)) from e
        except APIStatusError as e:
            raise ProviderError(f"{e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            raise ProviderError(f"Connection error: {e}") from e

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        system, msgs = self._extract_system(request.messages)
        native = [_message_to_anthropic(m) for m in msgs]
        tools = [t.to_anthropic() for t in request.tools] if request.tools else None
        self._current_tool = None
        try:
            stream = await self.client.messages.create(
                model=request.model or self.default_model,
                max_tokens=request.max_tokens or 4096,
                messages=native,  # type: ignore[arg-type]
                system=system or "",
                tools=tools,  # type: ignore[arg-type]
                temperature=request.temperature or 1.0,
                stream=True,
                **request.extra,
            )
            async for event in stream:  # type: ignore[union-attr]
                etype = getattr(event, "type", "")
                if etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", "") == "text_delta":
                        yield StreamChunk(content=getattr(delta, "text", ""))
                    elif delta and getattr(delta, "type", "") == "input_json_delta":
                        if self._current_tool:
                            self._current_tool["arguments_json"] += getattr(delta, "partial_json", "")
                            yield StreamChunk(
                                tool_call=ToolCallChunk(
                                    id=self._current_tool["id"],
                                    arguments_delta=getattr(delta, "partial_json", ""),
                                )
                            )
                elif etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", "") == "tool_use":
                        self._current_tool = {
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                            "arguments_json": "",
                        }
                        yield StreamChunk(
                            tool_call=ToolCallChunk(
                                id=getattr(block, "id", ""),
                                name=getattr(block, "name", ""),
                                is_start=True,
                            )
                        )
                elif etype == "content_block_stop":
                    if self._current_tool:
                        yield StreamChunk(
                            tool_call=ToolCallChunk(
                                id=self._current_tool["id"],
                                name=self._current_tool["name"],
                                is_end=True,
                            )
                        )
                        self._current_tool = None
                elif etype == "message_delta":
                    delta = getattr(event, "delta", None)
                    finish = getattr(delta, "stop_reason", None) if delta else None
                    usage = None
                    e_usage = getattr(event, "usage", None)
                    if e_usage:
                        u_in = getattr(e_usage, "input_tokens", 0)
                        u_out = getattr(e_usage, "output_tokens", 0)
                        usage = Usage(
                            prompt_tokens=u_in,
                            completion_tokens=u_out,
                            total_tokens=u_in + u_out,
                        )
                    if finish:
                        yield StreamChunk(finish_reason=finish, usage=usage)
                elif etype == "message_stop":
                    pass
        except AnthropicAuthError as e:
            raise AuthenticationError(str(e)) from e
        except AnthropicRateLimitError as e:
            raise RateLimitError(str(e)) from e
        except APIStatusError as e:
            raise ProviderError(f"{e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            raise ProviderError(f"Connection error: {e}") from e

    async def list_models(self) -> list[str]:
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]
