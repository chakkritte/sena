"""Instruction tier management for persistent context."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import platformdirs


class InstructionTierManager:
    """Manages hierarchical instruction files (SENA.md, MEMORY.md)."""

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or Path.cwd()
        self.user_dir = Path(platformdirs.user_config_dir("sena"))
        self.global_memory_file = self.user_dir / "SENA.md"
        self.project_slug = self._get_project_slug()
        self.private_memory_dir = self.user_dir / "memory" / self.project_slug
        self.private_memory_index = self.private_memory_dir / "MEMORY.md"

    def _get_project_slug(self) -> str:
        """Create a unique slug for the current project directory."""
        path_str = str(self.root_dir.absolute())
        return hashlib.md5(path_str.encode()).hexdigest()[:12]

    def get_global_memory(self) -> str:
        """Read global personal memory."""
        if self.global_memory_file.exists():
            return self.global_memory_file.read_text(encoding="utf-8")
        return ""

    def get_private_project_memory(self) -> str:
        """Read private project memory.
        
        Loads MEMORY.md as the index, plus any sibling markdown files.
        """
        if not self.private_memory_dir.exists():
            return ""
            
        parts = []
        if self.private_memory_index.exists():
            parts.append(f"--- INDEX (MEMORY.md) ---\n{self.private_memory_index.read_text(encoding='utf-8')}")
            
        for md_file in self.private_memory_dir.glob("*.md"):
            if md_file == self.private_memory_index:
                continue
            parts.append(f"--- NOTE ({md_file.name}) ---\n{md_file.read_text(encoding='utf-8')}")
            
        return "\n\n".join(parts)

    def get_project_instructions(self) -> str:
        """Read project-wide instructions (SENA.md in root)."""
        project_file = self.root_dir / "SENA.md"
        if project_file.exists():
            return project_file.read_text(encoding="utf-8")
        return ""

    def get_scoped_instructions(self, current_dir: Optional[Path] = None) -> str:
        """Read subdirectory-specific instructions."""
        search_dir = current_dir or Path.cwd()
        # Find the nearest SENA.md going up until root_dir
        curr = search_dir
        while curr.exists() and curr.is_relative_to(self.root_dir):
            scoped_file = curr / "SENA.md"
            if scoped_file.exists() and scoped_file != (self.root_dir / "SENA.md"):
                return scoped_file.read_text(encoding="utf-8")
            if curr == self.root_dir:
                break
            curr = curr.parent
        return ""

    def aggregate(self, current_dir: Optional[Path] = None) -> str:
        """Aggregate all instruction tiers into a single prompt block."""
        sections = []
        
        global_mem = self.get_global_memory()
        if global_mem:
            sections.append(f"### GLOBAL PERSONAL MEMORY\n{global_mem}")
            
        private_mem = self.get_private_project_memory()
        if private_mem:
            sections.append(f"### PRIVATE PROJECT MEMORY\n{private_mem}")
            
        project_inst = self.get_project_instructions()
        if project_inst:
            sections.append(f"### PROJECT INSTRUCTIONS\n{project_inst}")
            
        scoped_inst = self.get_scoped_instructions(current_dir)
        if scoped_inst:
            sections.append(f"### SCOPED INSTRUCTIONS\n{scoped_inst}")
            
        if not sections:
            return ""
            
        return "\n\n".join(sections)
