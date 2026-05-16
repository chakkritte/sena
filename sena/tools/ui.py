"""Tool for updating the agent's current topic/status."""

from __future__ import annotations

from typing import Any, Optional

from sena.core.base import BaseTool, ToolResult


class UpdateTopicTool(BaseTool):
    """Updates the agent's current topic and strategic intent."""

    name = "update_topic"
    description = (
        "Updates the agent's current topic and strategic intent. "
        "Use this to keep the user informed during multi-step tasks. "
        "Provide a clear title and a concise summary of your current progress and next steps."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title of the new topic or chapter.",
            },
            "summary": {
                "type": "string",
                "description": "A detailed summary of work completed and current strategic intent.",
            },
            "strategic_intent": {
                "type": "string",
                "description": "A mandatory one-sentence statement of your immediate intent.",
            },
        },
        "required": ["strategic_intent"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        title = kwargs.get("title", "Update")
        summary = kwargs.get("summary", "")
        intent = kwargs["strategic_intent"]
        
        # In this implementation, we just print it to the console using a specific style
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        
        console = Console()
        content = Text()
        if summary:
            content.append(summary + "\n\n", style="dim")
        content.append(f"Intent: {intent}", style="bold cyan")
        
        console.print(
            Panel(
                content,
                title=f"[bold yellow]Topic: {title}[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
            )
        )
        
        return ToolResult(tool_call_id="", name=self.name, content=f"Topic updated: {title}")
