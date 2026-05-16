"""Ollama provider adapter.

Uses the OpenAI-compatible /v1/chat/completions endpoint when available,
with fallback to Ollama-native APIs for model discovery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from sena.core.base import BaseProvider
from sena.core.models import (
    CompletionRequest,
    CompletionResponse,
    ProviderInfo,
    StreamChunk,
)
from sena.providers.base import ProviderError
from sena.providers.openai import OpenAIProvider

logger = structlog.get_logger()


class OllamaProvider(BaseProvider):
    """Provider adapter for Ollama local LLM server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        # Ollama exposes an OpenAI-compatible endpoint at /v1
        self._openai = OpenAIProvider(
            api_key="ollama",  # unused but required by client
            base_url=f"{self.base_url}/v1",
            default_model=default_model,
            name="ollama",
        )
        self.info = ProviderInfo(
            name="ollama",
            supports_streaming=True,
            supports_tools=True,  # model-dependent
            supports_vision=False,
            supports_embeddings=True,
            default_model=default_model,
            requires_api_key=False,
            base_url=self.base_url,
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return await self._openai.complete(request)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        async for chunk in self._openai.stream(request):
            yield chunk

    async def list_models(self) -> list[str]:
        """Query Ollama /api/tags for available models."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return [self.default_model]

    async def pull_model(self, model: str) -> dict[str, Any]:
        """Pull a model via Ollama /api/pull."""
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model},
                )
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
        except Exception as e:
            raise ProviderError(f"Failed to pull model {model}: {e}") from e

    async def embeddings(self, model: str, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via Ollama /api/embed."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("embeddings", [])  # type: ignore[no-any-return]
        except Exception as e:
            raise ProviderError(f"Embedding request failed: {e}") from e
