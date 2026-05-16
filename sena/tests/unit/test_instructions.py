"""Unit tests for InstructionTierManager."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from sena.context.instructions import InstructionTierManager

@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create a mock home directory structure
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        
        # Create project root
        project_root = tmp_path / "project"
        project_root.mkdir()
        
        # Create subdirectory
        subdir = project_root / "src" / "deep"
        subdir.mkdir(parents=True)
        
        yield {
            "root": project_root,
            "home": home_dir,
            "subdir": subdir
        }

def test_instruction_tier_manager_aggregation(temp_workspace, monkeypatch):
    root = temp_workspace["root"]
    home = temp_workspace["home"]
    subdir = temp_workspace["subdir"]
    
    # Mock platformdirs to use our temp home
    monkeypatch.setattr("platformdirs.user_config_dir", lambda _: str(home / ".config" / "sena"))
    
    # Setup files
    global_sena = home / ".config" / "sena" / "SENA.md"
    global_sena.parent.mkdir(parents=True, exist_ok=True)
    global_sena.write_text("Global instructions", encoding="utf-8")
    
    project_sena = root / "SENA.md"
    project_sena.write_text("Project instructions", encoding="utf-8")
    
    scoped_sena = root / "src" / "SENA.md"
    scoped_sena.write_text("Scoped instructions", encoding="utf-8")
    
    itm = InstructionTierManager(root_dir=root)
    
    # Test aggregation in root
    agg_root = itm.aggregate()
    assert "Global instructions" in agg_root
    assert "Project instructions" in agg_root
    assert "Scoped instructions" not in agg_root # Aggregation at root doesn't include sub-scoped
    
    # Test aggregation in subdir
    agg_subdir = itm.aggregate(current_dir=subdir)
    assert "Global instructions" in agg_subdir
    assert "Project instructions" in agg_subdir
    assert "Scoped instructions" in agg_subdir

def test_private_memory_loading(temp_workspace, monkeypatch):
    root = temp_workspace["root"]
    home = temp_workspace["home"]
    
    monkeypatch.setattr("platformdirs.user_config_dir", lambda _: str(home / ".config" / "sena"))
    
    itm = InstructionTierManager(root_dir=root)
    memory_dir = itm.private_memory_dir
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    (memory_dir / "MEMORY.md").write_text("Index content", encoding="utf-8")
    (memory_dir / "note1.md").write_text("Note 1 content", encoding="utf-8")
    
    private_mem = itm.get_private_project_memory()
    assert "Index content" in private_mem
    assert "Note 1 content" in private_mem
    assert "MEMORY.md" in private_mem
    assert "note1.md" in private_mem
