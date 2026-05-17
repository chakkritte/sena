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
    
    console.print(" [bold white]Proceed?[/bold white]")
    console.print(" [bold green]y[/bold green] - Yes")
    console.print(" [bold yellow]a[/bold yellow] - Auto-Accept for this task")
    console.print(" [bold red]n[/bold red] - No")
    
    choice = Prompt.ask("", choices=["y", "a", "n"], default="y", show_choices=False)
    
    if choice == "a":
        _SESSION_AUTO_ACCEPT = True
        return True
    
    return choice == "y"


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
