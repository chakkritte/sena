"""CLI commands for AST and Git-aware documentation sync."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
import typer

from carbonclaw.cli.main import app, console
from carbonclaw.agents.docs import DocsAgent
from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.memory.sqlite import SQLiteMemory
from carbonclaw.providers.registry import ProviderRegistry


def get_git_modified_files() -> list[str]:
    """Retrieve list of modified or untracked Python files from Git."""
    try:
        # Check modified staged/unstaged files
        res = subprocess.run(
            ["git", "diff", "--name-only", "*.py"],
            capture_output=True,
            text=True,
            check=True
        )
        files = [f.strip() for f in res.stdout.splitlines() if f.strip().endswith(".py")]
        
        # Check untracked files
        res_untracked = subprocess.run(
            ["git", "status", "--porcelain", "*.py"],
            capture_output=True,
            text=True,
            check=True
        )
        for line in res_untracked.stdout.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0] == "??":
                f_path = parts[1].strip()
                if f_path not in files:
                    files.append(f_path)
                    
        return files
    except Exception:
        return []


def inject_docstring(filepath: str, name: str, docstring: str) -> bool:
    """Inject a docstring immediately below the function/class definition line."""
    path = Path(filepath)
    if not path.exists():
        return False
        
    lines = path.read_text(encoding="utf-8").splitlines()
    target_idx = -1
    indent = ""
    
    # Locate function/class line
    for idx, line in enumerate(lines):
        if (f"def {name}" in line or f"class {name}" in line) and ":" in line:
            target_idx = idx
            # Detect indentation
            indent = line[:-len(line.lstrip())] if line.strip() else ""
            break
            
    if target_idx == -1:
        return False
        
    # Format docstring with correct indentation
    doc_lines = [indent + "    " + l for l in docstring.splitlines()]
    
    # Insert docstring
    lines.insert(target_idx + 1, "\n".join(doc_lines))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


@app.command(name="doc-sync")
def doc_sync() -> None:
    """Audit modified Python files and auto-generate missing class/function docstrings."""
    config = CarbonClawConfig()
    
    async def _execute() -> None:
        provider = ProviderRegistry.create(config.default_provider, config)
        memory = SQLiteMemory()
        agent = DocsAgent(provider, [], memory, model=config.default_model)
        
        console.print("[dim]Checking Git repository status...[/dim]")
        modified_files = get_git_modified_files()
        
        if not modified_files:
            console.print("[green]✅ No modified Python files detected in Git repository.[/green]")
            return
            
        console.print(f"🔍 Found [cyan]{len(modified_files)}[/cyan] modified Python files. Auditing ASTs...")
        
        for file in modified_files:
            missing = await agent.audit_docstrings(file)
            if not missing:
                console.print(f"  [green]OK[/green] {file} (All docstrings present)")
                continue
                
            console.print(f"  [yellow]Audit[/yellow] {file}: Missing docstrings for [bold yellow]{len(missing)}[/bold yellow] elements.")
            
            for item in missing:
                console.print(f"    ✨ Synthesizing docstring for {item['type']} [cyan]{item['name']}[/cyan]...")
                try:
                    doc = await agent.generate_docstring(item["name"], item["code"])
                    success = inject_docstring(file, item["name"], doc)
                    if success:
                        console.print(f"      [green]Success:[/green] Injected docstring.")
                    else:
                        console.print(f"      [red]Failed:[/red] Could not locate definition line.")
                except Exception as e:
                    console.print(f"      [red]Error:[/red] {e}")

    asyncio.run(_execute())
