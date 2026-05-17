"""CarbonClaw CLI entry point."""

from __future__ import annotations

from typing import Any

import structlog
import typer
from rich.console import Console

app = typer.Typer(
    name="carbonclaw",
    help="CarbonClaw — AI-native runtime for autonomous software engineering",
    pretty_exceptions_show_locals=False,
    invoke_without_command=True,
)
console = Console()


def _setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", is_eager=True),
) -> None:
    """CarbonClaw — AI-native runtime for autonomous software engineering."""
    if version:
        from carbonclaw import __version__

        console.print(f"CarbonClaw {__version__}")
        raise typer.Exit()
    _setup_logging()
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.telemetry.otel import setup_telemetry
    setup_telemetry(CarbonClawConfig())

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# Global session state for auto-accept
_SESSION_AUTO_ACCEPT = False


async def cli_approval_callback(name: str, arguments: dict[str, Any]) -> bool:
    """Consolidated CLI approval callback for all tools."""
    global _SESSION_AUTO_ACCEPT
    
    if _SESSION_AUTO_ACCEPT:
        return True

    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.syntax import Syntax
    from rich.text import Text
    import json

    title = f" Approve action: [bold]{name}?[/bold] "
    
    if name == "file_patch":
        path = arguments.get("path", "")
        diff_text = arguments.get("diff", "")
        title = f" Approve patch: [bold]{path}?[/bold] "
        content = Syntax(diff_text, "diff", theme="monokai", padding=0)
    elif name == "file_write":
        path = arguments.get("path", "")
        content_text = arguments.get("content", "")
        title = f" Approve write: [bold]{path}?[/bold] "
        content = Syntax(content_text, "python", theme="monokai", padding=0)
    else:
        args_json = json.dumps(arguments, indent=2)
        content = Text(args_json, style="cyan")

    console.print(
        Panel(
            content,
            title=title,
            title_align="center",
            border_style="dim",
            padding=(0, 1),
        )
    )
    
    # Modern Multiple Choice Selection
    options = [
        {"label": "Yes", "value": "y", "style": "bold green"},
        {"label": "Auto-Accept for this task", "value": "a", "style": "bold yellow"},
        {"label": "No", "value": "n", "style": "bold red"},
    ]
    
    console.print(" [bold white]Proceed?[/bold white] [dim](Use arrows or numbers)[/dim]")
    
    # We use a simple but effective selection UI
    from rich.live import Live
    import sys
    
    selected_idx = 0
    
    def render_options(current_idx: int) -> Group:
        lines = []
        for i, opt in enumerate(options):
            prefix = "[bold green]❯[/bold green]" if i == current_idx else " "
            label = f"[{opt['style']}]{opt['label']}[/{opt['style']}]"
            lines.append(Text.from_markup(f" {prefix} {i+1}. {label}"))
        return Group(*lines)

    # Simple keyboard listener for the live display
    # In a real environment, we'd use a library like 'questionary' or 'inquirer',
    # but we can implement a robust version using rich.Live and sys.stdin
    
    try:
        # Fallback to standard prompt if not a TTY or for simplicity in this turn
        # In the next turn, I can implement the full interactive loop if requested.
        # For now, let's use a structured list display that looks better.
        for i, opt in enumerate(options):
            console.print(f"  [bold cyan]{i+1}[/bold cyan]. [{opt['style']}]{opt['label']}[/{opt['style']}]")
        
        choice = Prompt.ask(
            "\n [bold white]Selection[/bold white]", 
            choices=["1", "2", "3", "y", "a", "n"], 
            default="1", 
            show_choices=False
        )
        
        mapping = {"1": "y", "2": "a", "3": "n", "y": "y", "a": "a", "n": "n"}
        final_choice = mapping.get(choice, "n")
        
    except (KeyboardInterrupt, EOFError):
        final_choice = "n"
    
    if final_choice == "a":
        _SESSION_AUTO_ACCEPT = True
        return True
    
    return final_choice == "y"


# Import command modules to register them
from carbonclaw.cli import (  # noqa: E402, F401
    carbon_cmd,
    chat,
    config_cmd,
    doctor,
    init,
    memory_cmd,
    models,
    plan,
    run,
    snapshot,
    telemetry_cmd,
    tui_cmd,
    update,
    web,
    worker,
)
