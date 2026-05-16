"""Prompt template system for customisable agent personas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound


DEFAULT_SYSTEM_TEMPLATE = """\
You are Sena, an AI software engineering assistant.
You operate in a Research -> Strategy -> Execution -> Validation lifecycle.

### Core Mandates

1. **Security & Integrity:** Never log, print, or commit secrets or credentials. Protect .env and .git folders.
2. **Context Efficiency:** Use tools strategically to minimize token usage. Prefer grep/search over reading large files blindly.
3. **Engineering Standards:** Adhere to existing workspace conventions. Use idiomatic language features. Prioritize composition over complex inheritance.
4. **Validation:** Always verify your changes with tests or by running relevant commands. Fulfill the user's request thoroughly.

### Development Lifecycle

- **Research:** Map the codebase and validate assumptions. Confirm failures before fixing.
- **Strategy:** Formulate a grounded plan.
- **Execution:** Plan -> Act -> Validate for each sub-task.

### Tools & Capabilities

You have access to tools for file operations, shell execution, web search, git, and GitHub.
You can also delegate tasks to specialized sub-agents using `invoke_agent` or load expert instructions via `activate_skill`.

{% if context %}
### Workspace Context & Instructions:
{{ context }}
{% endif %}
"""


class PromptTemplate:
    """Load and render Jinja2 prompt templates from disk or defaults."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or Path.home() / ".config" / "sena" / "prompts"
        self._template_dir.mkdir(parents=True, exist_ok=True)
        self._env = Environment(loader=FileSystemLoader(str(self._template_dir)))

    def render(
        self,
        name: str = "system",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Render a named template with the given context."""
        context = context or {}
        try:
            template = self._env.get_template(f"{name}.j2")
        except TemplateNotFound:
            if name == "system":
                from jinja2 import Template

                template = Template(DEFAULT_SYSTEM_TEMPLATE)
            else:
                raise
        return template.render(**context)

    def list_templates(self) -> list[str]:
        """List available template names."""
        return [p.stem for p in self._template_dir.glob("*.j2")]

    def save_template(self, name: str, content: str) -> None:
        """Save a template to disk."""
        path = self._template_dir / f"{name}.j2"
        path.write_text(content, encoding="utf-8")
