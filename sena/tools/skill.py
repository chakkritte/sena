"""Tool for activating specialized agent skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import platformdirs

from sena.core.base import BaseTool, ToolResult


class ActivateSkillTool(BaseTool):
    """Activates a specialized agent skill by name."""

    name = "activate_skill"
    description = (
        "Activates a specialized agent skill by name. "
        "Returns the skill's instructions wrapped in <activated_skill> tags. "
        "These provide specialized guidance for the current task."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the skill to activate (e.g., 'skill-creator', 'security-audit').",
            },
        },
        "required": ["name"],
    }

    def __init__(self, skills_dir: Optional[Path] = None) -> None:
        super().__init__()
        self.skills_dir = skills_dir or Path(platformdirs.user_config_dir("sena")) / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs["name"]
        skill_file = self.skills_dir / f"{name}.md"
        
        # Also check in project root if it exists
        project_skill_file = Path.cwd() / ".sena" / "skills" / f"{name}.md"
        
        target_file = None
        if project_skill_file.exists():
            target_file = project_skill_file
        elif skill_file.exists():
            target_file = skill_file
            
        if target_file:
            content = target_file.read_text(encoding="utf-8")
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"<activated_skill>\n{content}\n</activated_skill>"
            )
            
        return ToolResult(
            tool_call_id="",
            name=self.name,
            content=f"Error: Skill '{name}' not found. Available skills: "
            + ", ".join([p.stem for p in self.skills_dir.glob("*.md")]),
            is_error=True
        )
