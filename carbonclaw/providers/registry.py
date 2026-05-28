"""Provider factory and registry."""

from __future__ import annotations

import structlog

from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.core.base import BaseProvider
from carbonclaw.providers.anthropic import AnthropicProvider
from carbonclaw.providers.gemini import GeminiProvider
from carbonclaw.providers.ollama import OllamaProvider
from carbonclaw.providers.openai import OpenAIProvider

logger = structlog.get_logger()

_PROVIDER_MAP: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenAIProvider,
    "deepseek": OpenAIProvider,
}


class ProviderRegistry:
    """Create provider instances from configuration."""

    @classmethod
    def create(cls, name: str, config: CarbonClawConfig | None = None) -> BaseProvider:
        cfg = config or CarbonClawConfig()
        provider_cfg = cfg.get_provider_config(name)
        provider_cls = _PROVIDER_MAP.get(name.lower())
        if provider_cls is None:
            raise ValueError(f"Unknown provider: {name}")

        api_key = provider_cfg.api_key
        base_url = provider_cfg.base_url
        default_model = provider_cfg.default_model or cfg.default_model

        if name == "ollama":
            return OllamaProvider(
                base_url=base_url or "http://localhost:11434",
                default_model=default_model,
            )

        if name in ("openrouter", "deepseek"):
            if not api_key:
                raise ValueError(f"Provider '{name}' requires an API key.")
            return OpenAIProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=default_model,
                name=name,
            )

        if not api_key:
            raise ValueError(f"Provider '{name}' requires an API key.")

        return provider_cls(  # type: ignore[call-arg]
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
        )

    @classmethod
    def available(cls) -> list[str]:
        return list(_PROVIDER_MAP.keys())

    @classmethod
    def register(cls, name: str, provider_cls: type[BaseProvider]) -> None:
        _PROVIDER_MAP[name.lower()] = provider_cls
