"""Layered configuration system for Sena."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import platformdirs
import structlog
from pydantic import Field, BaseModel
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = structlog.get_logger()


class ProviderCredential(BaseModel):
    """Credentials for a single provider."""

    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None


class _ProjectSource(PydanticBaseSettingsSource):
    """Load project-level config from pyproject.toml [tool.sena]."""

    def get_field_value(
        self, field: "FieldInfo", field_name: str
    ) -> tuple[Any, str, bool]:
        pyproject = Path("pyproject.toml")
        if not pyproject.exists():
            return None, field_name, False
        try:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
            value = data.get("tool", {}).get("sena", {}).get(field_name)
            return value, field_name, value is not None
        except Exception:
            return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        pyproject = Path("pyproject.toml")
        if not pyproject.exists():
            return {}
        try:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
            return data.get("tool", {}).get("sena", {})  # type: ignore[no-any-return]
        except Exception:
            return {}


class _UserSource(PydanticBaseSettingsSource):
    """Load user-level config from ~/.config/sena/config.toml."""

    def get_field_value(
        self, field: "FieldInfo", field_name: str
    ) -> tuple[Any, str, bool]:
        path = Path(platformdirs.user_config_dir("sena")) / "config.toml"
        if not path.exists():
            return None, field_name, False
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            value = data.get(field_name)
            return value, field_name, value is not None
        except Exception:
            return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = Path(platformdirs.user_config_dir("sena")) / "config.toml"
        if not path.exists():
            return {}
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}


class _PersonaSource(PydanticBaseSettingsSource):
    """Load agent persona from ~/.config/sena/persona.toml."""

    def get_field_value(
        self, field: "FieldInfo", field_name: str
    ) -> tuple[Any, str, bool]:
        if field_name != "persona":
            return None, field_name, False

        path = Path(platformdirs.user_config_dir("sena")) / "persona.toml"
        if not path.exists():
            return None, field_name, False
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            return data.get("persona"), field_name, True
        except Exception:
            return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = Path(platformdirs.user_config_dir("sena")) / "persona.toml"
        if not path.exists():
            return {}
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
                return {"persona": data.get("persona", {})}
        except Exception:
            return {}


class SenaConfig(BaseSettings):
    """Sena runtime configuration.

    Resolution order (highest to lowest priority):
    1. CLI arguments / code overrides
    2. Environment variables (SENA_*)
    3. Project config (pyproject.toml [tool.sena])
    4. User config (~/.config/sena/config.toml)
    5. Persona config (~/.config/sena/persona.toml)
    6. Defaults defined here
    """

    model_config = SettingsConfigDict(
        env_prefix="SENA_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # General
    default_provider: str = "ollama"
    default_model: str = "llama3.2"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None

    # Persona
    persona: dict[str, str] = Field(default_factory=dict)

    # Runtime policies
    auto_approve_safe_commands: bool = False
    auto_approve_file_writes: bool = False
    sandbox_enabled: bool = False
    sandbox_image: str = "sena-sandbox:latest"

    # Observability
    otel_endpoint: str | None = None
    timeout: int = 120

    # UI
    theme: str = "default"
    streaming: bool = True
    markdown: bool = True
    syntax_theme: str = "monokai"

    # Telemetry
    telemetry_enabled: bool = False
    telemetry_endpoint: str | None = None

    # Memory
    memory_backend: str = "sqlite"
    memory_path: str | None = None
    vector_backend: str | None = None

    # MCP
    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Providers (nested)
    openai: ProviderCredential = Field(default_factory=ProviderCredential)
    anthropic: ProviderCredential = Field(default_factory=ProviderCredential)
    gemini: ProviderCredential = Field(default_factory=ProviderCredential)
    ollama: ProviderCredential = Field(default_factory=ProviderCredential)
    openrouter: ProviderCredential = Field(default_factory=ProviderCredential)
    deepseek: ProviderCredential = Field(default_factory=ProviderCredential)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            _ProjectSource(settings_cls),
            _UserSource(settings_cls),
            _PersonaSource(settings_cls),
        )

    def get_provider_config(self, name: str) -> ProviderCredential:
        """Return the credential block for a named provider."""
        mapping: dict[str, ProviderCredential] = {
            "openai": self.openai,
            "anthropic": self.anthropic,
            "gemini": self.gemini,
            "ollama": self.ollama,
            "openrouter": self.openrouter,
            "deepseek": self.deepseek,
        }
        cred = mapping.get(name.lower(), ProviderCredential())
        
        # Fallback to top-level fields if not specified in the provider block
        if cred.api_key is None and name.lower() == self.default_provider.lower():
            cred.api_key = self.api_key
        if cred.base_url is None and name.lower() == self.default_provider.lower():
            cred.base_url = self.base_url
        if cred.default_model is None and name.lower() == self.default_provider.lower():
            cred.default_model = self.default_model
            
        return cred

    @staticmethod
    def user_dir() -> Path:
        """Return the Sena user configuration directory."""
        return Path(platformdirs.user_config_dir("sena"))

    @staticmethod
    def ensure_user_dir() -> Path:
        """Create and return the Sena user configuration directory."""
        path = SenaConfig.user_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path
