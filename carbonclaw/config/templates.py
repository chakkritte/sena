"""Agent template marketplace configuration loader and manager for CarbonClaw."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic import BaseModel, Field


class AgentTemplate(BaseModel):
    """Configuration for a shareable, specialized agent configuration."""

    name: str
    description: str
    default_provider: str = "ollama"
    default_model: str = "llama3.2"
    routing_strategy: str = "sustainability"
    temperature: float = 0.7
    tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None


class TemplateManager:
    """Manages downloading, listing, and publishing agent templates."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the template manager."""
        if path is None:
            path = Path(user_config_dir("carbonclaw")) / "templates"
        self._path = path
        self._path.mkdir(parents=True, exist_ok=True)

    def save_template(self, template: AgentTemplate) -> Path:
        """Save a template config locally."""
        file_path = self._path / f"{template.name}.json"
        file_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")
        return file_path

    def load_template(self, name: str) -> AgentTemplate | None:
        """Load a local template configuration by name."""
        file_path = self._path / f"{name}.json"
        if not file_path.exists():
            return None
        try:
            return AgentTemplate.model_validate_json(file_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_templates(self) -> list[AgentTemplate]:
        """List all locally available templates."""
        results: list[AgentTemplate] = []
        for file_path in self._path.glob("*.json"):
            try:
                results.append(AgentTemplate.model_validate_json(file_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def mock_pull(self, name: str) -> AgentTemplate | None:
        """Simulate pulling a template from a remote marketplace registry."""
        registry = {
            "sustainability-swarm": AgentTemplate(
                name="sustainability-swarm",
                description="Lightweight research/coding swarm using zero-carbon local models.",
                default_provider="ollama",
                default_model="llama3.2",
                routing_strategy="sustainability",
                tools=["file_read", "file_write", "git"],
                system_prompt="You are a green-focused coder. Write code with minimal iterations.",
            ),
            "fast-coder": AgentTemplate(
                name="fast-coder",
                description="High-velocity cloud coding template using DeepSeek/OpenRouter.",
                default_provider="deepseek",
                default_model="deepseek-coder",
                routing_strategy="latency",
                tools=["shell", "file_write", "file_patch"],
            ),
        }
        
        template = registry.get(name.lower())
        if template:
            self.save_template(template)
        return template
