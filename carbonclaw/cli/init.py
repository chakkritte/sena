"""Interactive persona initialization command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from carbonclaw.cli.main import app
from carbonclaw.config.settings import CarbonClawConfig

console = Console()


@app.command(name="setup")
def setup_carbonclaw() -> None:
    """Alias for 'init' - Run the CarbonClaw setup wizard."""
    init_carbonclaw()


@app.command(name="init")
def init_carbonclaw() -> None:
    """Run the CarbonClaw setup wizard to configure providers, persona, and project settings."""
    console.print(
        Panel(
            "[bold green]🤖 Welcome to CarbonClaw Setup[/bold green]\n"
            "This wizard will help you configure your AI environment, "
            "sustainability preferences, and agent persona.",
            border_style="green",
        )
    )

    config_dir = CarbonClawConfig.ensure_user_dir()
    config_path = config_dir / "config.toml"
    persona_path = config_dir / "persona.toml"

    # --- 1. Core Configuration ---
    console.print("\n[bold cyan]1. Core Configuration[/bold cyan]")
    
    provider = Prompt.ask(
        "Default LLM Provider",
        choices=["ollama", "openai", "anthropic", "gemini", "deepseek", "openrouter"],
        default="ollama",
    )
    
    config_data: dict[str, Any] = {
        "default_provider": provider,
    }

    if provider != "ollama":
        api_key = Prompt.ask(f"Enter your {provider.upper()} API Key", password=True)
        if api_key:
            # We'll store it in the provider-specific block
            config_data[provider] = {"api_key": api_key}
    elif provider == "ollama":
        base_url = Prompt.ask("Ollama Base URL", default="http://localhost:11434")
        config_data["ollama"] = {"base_url": base_url}

    config_data["default_model"] = Prompt.ask(
        "Default Model ID",
        default="gemma4:e2b" if provider == "ollama" else "gpt-4o-mini",
    )

    # --- 2. Sustainability & Runtime ---
    console.print("\n[bold cyan]2. Sustainability & Runtime[/bold cyan]")
    
    config_data["carbon_tracking_enabled"] = Confirm.ask(
        "Enable real-time Carbon Emission tracking?", default=True
    )
    
    config_data["auto_approve_safe_commands"] = Confirm.ask(
        "Auto-approve safe shell commands (ls, git status, etc.)?", default=False
    )

    # --- 3. Persona ---
    console.print("\n[bold cyan]3. Agent Persona[/bold cyan]")
    if Confirm.ask("Would you like to customize your agent's persona now?", default=True):
        persona: dict[str, str] = {}
        persona["user_name"] = Prompt.ask("What should CarbonClaw call you?", default="User")
        persona["role"] = Prompt.ask("Agent primary role", default="Senior Software Engineer")
        persona["tone"] = Prompt.ask("Preferred tone", default="Concise and technical")
        
        import tomli_w
        with open(persona_path, "wb") as f:
            tomli_w.dump({"persona": persona}, f)
        console.print(f"[dim]Persona saved to {persona_path}[/dim]")

    # Save Config
    import tomli_w
    with open(config_path, "wb") as f:
        tomli_w.dump(config_data, f)
    
    console.print(f"\n[green]✔ Configuration saved to [bold]{config_path}[/bold][/green]")

    # --- 4. Project Setup ---
    console.print("\n[bold cyan]4. Project Context[/bold cyan]")
    if (Path.cwd() / ".git").exists():
        if Confirm.ask("Current directory is a Git repo. Create CARBONCLAW.md for project-specific instructions?", default=True):
            cc_md = Path("CARBONCLAW.md")
            if not cc_md.exists() or Confirm.ask("CARBONCLAW.md exists. Overwrite?"):
                cc_md.write_text(
                    "# Project Context\n\n"
                    "## Tech Stack\n- [Add languages/frameworks here]\n\n"
                    "## Instructions\n- [Add project-specific rules here]\n",
                    encoding="utf-8"
                )
                console.print("[green]✔ CARBONCLAW.md created.[/green]")

    console.print(
        "\n[bold green]Setup Complete![/bold green] "
        "Run [bold]carbonclaw chat[/bold] to begin your first session. 🚀\n"
    )
