"""Google Gemini provider adapter using the unified google-genai SDK."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from google.genai import Client
from google.genai.types import (
    Content,
    FunctionDeclaration,
    GenerateContentConfig,
    Part,
    Tool,
)

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
from carbonclaw.providers.base import ProviderError

logger = structlog.get_logger()


class GeminiProvider(BaseProvider):
    """Provider adapter for Google Gemini."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.0-flash-exp",
    ) -> None:
        super().__init__({
            "api_key": api_key,
            "default_model": default_model,
        })
        self.client = Client(api_key=api_key)
        self.default_model = default_model
        self.info = ProviderInfo(
            name="gemini",
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_embeddings=False,
            default_model=default_model,
            requires_api_key=True,
            base_url="https://generativelanguage.googleapis.com",
        )

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[Content]]:
        system_text: str | None = None
        contents: list[Content] = []
        for msg in messages:
            if msg.role == "system":
                system_text = msg.content
                continue
            if msg.role == "tool":
                contents.append(
                    Content(
                        role="user",
                        parts=[Part.from_function_response(
                            name=msg.name or "unknown",
                            response={"result": msg.content or ""},
                        )],
                    )
                )
                continue
            if msg.tool_calls:
                parts: list[Part] = []
                if msg.content:
                    parts.append(Part.from_text(text=msg.content))
                for tc in msg.tool_calls:
                    parts.append(
                        Part.from_function_call(
                            name=tc.name,
                            args=tc.arguments,
                        )
                    )
                contents.append(Content(role="model", parts=parts))
                continue
            contents.append(
                Content(
                    role="user" if msg.role == "user" else "model",
                    parts=[Part.from_text(text=msg.content or "")],
                )
            )
        return system_text, contents

    def _convert_tools(self, tools: list[Any]) -> list[Tool] | None:
        if not tools:
            return None
        decls: list[FunctionDeclaration] = []
        for t in tools:
            name = t.name if hasattr(t, "name") else t.get("name")
            desc = t.description if hasattr(t, "description") else t.get("description")
            params = t.parameters if hasattr(t, "parameters") else t.get("parameters", {})
            decls.append(
                FunctionDeclaration(
                    name=name,
                    description=desc,
                    parameters=params,
                )
            )
        return [Tool(function_declarations=decls)]

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        system, contents = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)
        config = GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            system_instruction=system,
            tools=tools,  # type: ignore[arg-type]
            **request.extra,
        )
        try:
            response = await self.client.models.generate_content(  # type: ignore[misc]
                model=request.model or self.default_model,
                contents=contents,
                config=config,
            )
            text = ""
            tool_calls: list[Any] = []
            for candidate in response.candidates or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", []) if content else []:
                    if part.text:
                        text += part.text
                    if part.function_call:
                        tool_calls.append(
                            {
                                "id": part.function_call.name or "",
                                "name": part.function_call.name or "",
                                "arguments": getattr(part.function_call, "args", {}),
                            }
                        )
            message = Message(
                role="assistant",
                content=text or None,
                tool_calls=tool_calls or None,
            )
            usage_meta = getattr(response, "usage_metadata", None)
            usage = Usage(
                prompt_tokens=getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
                completion_tokens=getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
                total_tokens=getattr(usage_meta, "total_token_count", 0) if usage_meta else 0,
            )
            return CompletionResponse(
                message=message,
                usage=usage,
                model=request.model or self.default_model,
                provider="gemini",
            )
        except Exception as e:
            raise ProviderError(f"Gemini completion failed: {e}") from e

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        system, contents = self._convert_messages(request.messages)
        tools = self._convert_tools(request.tools)
        config = GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            system_instruction=system,
            tools=tools,  # type: ignore[arg-type]
            **request.extra,
        )
        try:
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=request.model or self.default_model,
                contents=contents,
                config=config,
            ):
                text = ""
                tool_call_start: ToolCallChunk | None = None
                for candidate in getattr(chunk, "candidates", []) or []:
                    content = getattr(candidate, "content", None)
                    for part in getattr(content, "parts", []) if content else []:
                        if part.text:
                            text += part.text
                        if part.function_call:
                            tool_call_start = ToolCallChunk(
                                id=part.function_call.name or "",
                                name=part.function_call.name or "",
                                is_start=True,
                            )
                if text:
                    yield StreamChunk(content=text)
                if tool_call_start:
                    yield StreamChunk(tool_call=tool_call_start)
                # Usage and finish reason are usually on the final chunk
                if chunk.usage_metadata:
                    yield StreamChunk(
                        usage=Usage(
                            prompt_tokens=chunk.usage_metadata.prompt_token_count or 0,
                            completion_tokens=chunk.usage_metadata.candidates_token_count or 0,
                            total_tokens=chunk.usage_metadata.total_token_count or 0,
                        )
                    )
        except Exception as e:
            raise ProviderError(f"Gemini streaming failed: {e}") from e

    async def list_models(self) -> list[str]:
        try:
            models = self.client.models.list()
            return [m.name for m in models if m.name]
        except Exception:
            return [self.default_model]

