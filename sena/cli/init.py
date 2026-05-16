"""Interactive persona initialization command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from sena.cli.main import app

console = Console()


@app.command(name="init")
def init_persona() -> None:
    """Initialize a custom agent persona via an interactive wizard."""
    console.print(
        Panel.fit(
            "[bold blue]Sena Persona Initialization[/bold blue]\n"
            "Answer 10 questions to help Sena understand your preferences.",
            border_style="blue",
        )
    )

    persona: dict[str, str] = {}

    # 0. User Name
    persona["user_name"] = Prompt.ask(
        "0. [bold]Name[/bold]: What should Sena call you?",
        default="User",
    )

    # 1. Role
    persona["role"] = Prompt.ask(
        "1. [bold]Role[/bold]: What is the primary role of this agent?\n"
        "(e.g., Senior Fullstack Engineer, Data Scientist, Security Researcher)",
        default="Senior Software Engineer",
    )

    # 2. Tone
    persona["tone"] = Prompt.ask(
        "2. [bold]Tone[/bold]: What is the preferred communication style?\n"
        "(e.g., Concise and technical, Tutorial-like and verbose, Friendly but professional)",
        default="Concise and technical",
    )

    # 3. Formatting
    persona["formatting"] = Prompt.ask(
        "3. [bold]Formatting[/bold]: What are the strict code formatting/linting rules?\n"
        "(e.g., PEP8, Airbnb Style Guide, Use 2-space indentation)",
        default="Modern Python standards (Black, Ruff)",
    )

    # 4. TDD
    persona["tdd"] = Prompt.ask(
        "4. [bold]TDD[/bold]: How should the agent approach testing?\n"
        "(e.g., Write tests before code, Parallel tests, Integration focus)",
        default="Write unit tests for every logic change",
    )

    # 5. Error Handling
    persona["error_handling"] = Prompt.ask(
        "5. [bold]Error Handling[/bold]: What is the preferred strategy for exceptions?\n"
        "(e.g., Fail fast, Exhaustive logging, Automatic retries)",
        default="Exhaustive logging and fail-fast for clarity",
    )

    # 6. Autonomy
    persona["autonomy"] = Prompt.ask(
        "6. [bold]Autonomy[/bold]: How aggressively should it use tools without asking?\n"
        "(e.g., Always ask, Ask for destructive actions, Fully autonomous)",
        default="Ask for destructive actions",
    )

    # 7. Prioritization
    persona["prioritization"] = Prompt.ask(
        "7. [bold]Prioritization[/bold]: Optimize for speed, readability, or robustness?\n",
        choices=["speed", "readability", "robustness"],
        default="readability",
    )

    # 8. Expertise
    persona["expertise"] = Prompt.ask(
        "8. [bold]Expertise[/bold]: Primary languages/frameworks it should consider itself an expert in?\n",
        default="Python, FastAPI, React, TypeScript",
    )

    # 9. Feedback Reception
    persona["feedback_reception"] = Prompt.ask(
        "9. [bold]Feedback Reception[/bold]: How should it react to being corrected?\n"
        "(e.g., Apologize and update rules, Debate the correction, Silently update)",
        default="Update learned rules and acknowledge immediately",
    )

    # 10. Goal
    persona["goal"] = Prompt.ask(
        "10. [bold]Goal[/bold]: What is the ultimate metric of success for this agent?\n"
        "(e.g., Pass all tests, 100% type coverage, Most readable code)",
        default="Functional, tested, and maintainable code",
    )

    # Save to ~/.config/sena/persona.toml
    from sena.config.settings import SenaConfig
    import os

    config_dir = Path(typer.get_app_dir("sena"))
    config_dir.mkdir(parents=True, exist_ok=True)
    persona_path = config_dir / "persona.toml"

    import tomli_w
    with open(persona_path, "wb") as f:
        tomli_w.dump({"persona": persona}, f)

    console.print(f"\n[green]Success![/green] Persona saved to [bold]{persona_path}[/bold]")
    
    if Confirm.ask("\nWould you like to create a project-specific [bold]SENA.md[/bold] in the current directory?"):
        sena_md = Path("SENA.md")
        if sena_md.exists():
            if not Confirm.ask("SENA.md already exists. Overwrite?"):
                console.print("[yellow]Skipped SENA.md creation.[/yellow]")
            else:
                sena_md.write_text("# Project Instructions\n\n- Add your project-specific conventions here.\n", encoding="utf-8")
                console.print("[green]SENA.md updated.[/green]")
        else:
            sena_md.write_text("# Project Instructions\n\n- Add your project-specific conventions here.\n", encoding="utf-8")
            console.print("[green]SENA.md created.[/green]")

    console.print("Sena will now use this persona and context for all future interactions.")
