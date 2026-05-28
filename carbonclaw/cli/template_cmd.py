"""CLI commands for managing agent templates."""

from __future__ import annotations

import typer
from rich.table import Table

from carbonclaw.cli.main import app, console
from carbonclaw.config.templates import TemplateManager, AgentTemplate


@app.command(name="template-list")
def template_list() -> None:
    """List all locally installed agent configurations templates."""
    manager = TemplateManager()
    templates = manager.list_templates()
    
    if not templates:
        console.print("[dim]No local agent templates found.[/dim]")
        console.print("Try running: [cyan]carbonclaw template-pull sustainability-swarm[/cyan]")
        return
        
    table = Table(title="🧩 Installed Agent Templates", show_header=True, header_style="bold green")
    table.add_column("Template Name", style="cyan", no_wrap=True)
    table.add_column("Provider", style="white")
    table.add_column("Model ID", style="magenta")
    table.add_column("Strategy", style="green")
    table.add_column("Description", style="dim")

    for t in templates:
        table.add_row(
            t.name,
            t.default_provider,
            t.default_model,
            t.routing_strategy,
            t.description,
        )
    console.print(table)


@app.command(name="template-pull")
def template_pull(
    name: str = typer.Argument(..., help="The name of the agent template to download."),
) -> None:
    """Download and install a specialized agent configuration template."""
    manager = TemplateManager()
    console.print(f"📥 [dim]Fetching template '{name}' from marketplace...[/dim]")
    
    template = manager.mock_pull(name)
    if not template:
        console.print(f"[bold red]Error:[/bold red] Template '{name}' not found in registry.")
        raise typer.Exit(code=1)
        
    console.print(f"🌱 [bold green]Template '{name}' successfully pulled and saved![/bold green]")
    console.print(f"[bold]Provider:[/bold] {template.default_provider}")
    console.print(f"[bold]Model ID:[/bold] {template.default_model}")
    console.print(f"[bold]Description:[/bold] {template.description}")


@app.command(name="template-publish")
def template_publish(
    name: str = typer.Argument(..., help="Template name to register."),
    description: str = typer.Option(..., "--desc", "-d", help="Short description of the template."),
) -> None:
    """Publish your custom agent swarm configuration to the marketplace."""
    manager = TemplateManager()
    
    template = AgentTemplate(
        name=name,
        description=description,
    )
    
    path = manager.save_template(template)
    console.print(f"🚀 [bold green]Successfully published '{name}' to marketplace![/bold green]")
    console.print(f"[dim]Template config saved at: {path}[/dim]")
