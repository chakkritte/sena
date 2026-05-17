"""OpenAI-compatible provider adapter.

Also covers DeepSeek, OpenRouter, Azure, and any local endpoint
implementing the OpenAI Chat Completions API.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from openai import AsyncOpenAI
from openai._exceptions import APIConnectionError, APIStatusError
from openai._exceptions import AuthenticationError as OAIAuthError
from openai._exceptions import RateLimitError as OAIRateLimitError

from carbonclaw.core.base import BaseProvider
from carbonclaw.core.models import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ProviderInfo,
    StreamChunk,
    ToolCallChunk,
    Usage,
)
from carbonclaw.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
    ToolAccumulator,
    _message_to_openai,
)

logger = structlog.get_logger()


from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class OpenAIProvider(BaseProvider):
    """Provider adapter for OpenAI and OpenAI-compatible endpoints."""

    # ... (init unchanged) ...

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, ProviderError)),
        reraise=True,
    )
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = [_message_to_openai(m) for m in request.messages]
        # ... (rest of method unchanged) ...
        tools = [t.to_openai() for t in request.tools] if request.tools else None
        try:
            response = await self.client.chat.completions.create(
                model=request.model or self.default_model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
                **request.extra,
            )
            choice = getattr(response, "choices")[0]
            msg = choice.message
            tool_calls: list[Any] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        func = getattr(tc, "function")
                        args = json.loads(getattr(func, "arguments")) if getattr(func, "arguments") else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({"id": getattr(tc, "id"), "name": getattr(func, "name"), "arguments": args})
            message = Message(
                role="assistant",
                content=msg.content,
                tool_calls=tool_calls,
            )
            resp_usage = getattr(response, "usage", None)
            usage = Usage(
                prompt_tokens=getattr(resp_usage, "prompt_tokens", 0) if resp_usage else 0,
                completion_tokens=getattr(resp_usage, "completion_tokens", 0) if resp_usage else 0,
                total_tokens=getattr(resp_usage, "total_tokens", 0) if resp_usage else 0,
            )
            return CompletionResponse(
                message=message,
                usage=usage,
                model=getattr(response, "model", self.default_model),
                provider=self.name,
            )
        except OAIAuthError as e:
            raise AuthenticationError(str(e)) from e
        except OAIRateLimitError as e:
            raise RateLimitError(str(e)) from e
        except APIStatusError as e:
            raise ProviderError(f"{e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            raise ProviderError(f"Connection error: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, ProviderError)),
        reraise=True,
    )
    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        messages = [_message_to_openai(m) for m in request.messages]
        tools = [t.to_openai() for t in request.tools] if request.tools else None
        self._tool_accum = ToolAccumulator()
        try:
            stream = await self.client.chat.completions.create(
                model=request.model or self.default_model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
                **request.extra,
            )
            async for chunk in stream:  # type: ignore[union-attr]
                choices = getattr(chunk, "choices", [])
                delta = choices[0].delta if choices else None
                if not delta:
                    continue
                # Text content
                if delta.content:
                    yield StreamChunk(content=delta.content)
                # Tool calls
                if delta.tool_calls:
                    for tc_chunk in self._tool_accum.ingest(delta.tool_calls):
                        yield tc_chunk
                # Finish
                if choices[0].finish_reason:
                    # Flush remaining tool calls
                    for tc in self._tool_accum.flush():
                        yield StreamChunk(
                            tool_call=ToolCallChunk(
                                id=tc.id,
                                name=tc.name,
                                is_end=True,
                            )
                        )
                    usage = None
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage:
                        usage = Usage(
                            prompt_tokens=getattr(chunk_usage, "prompt_tokens", 0),
                            completion_tokens=getattr(chunk_usage, "completion_tokens", 0),
                            total_tokens=getattr(chunk_usage, "total_tokens", 0),
                        )
                    yield StreamChunk(finish_reason=choices[0].finish_reason, usage=usage)
        except OAIAuthError as e:
            raise AuthenticationError(str(e)) from e
        except OAIRateLimitError as e:
            raise RateLimitError(str(e)) from e
        except APIStatusError as e:
            raise ProviderError(f"{e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            raise ProviderError(f"Connection error: {e}") from e

    async def list_models(self) -> list[str]:
        try:
            models = await self.client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return []
