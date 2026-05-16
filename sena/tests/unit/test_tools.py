"""Unit tests for the tool system."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sena.tools.base import ToolRegistry
from sena.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from sena.tools.git import GitTool
from sena.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_tool_echo() -> None:
    """Shell tool should execute a command and return stdout."""
    tool = ShellTool()
    result = await tool.execute({"command": "echo hello", "timeout": 5})
    assert not result.is_error
    assert "hello" in result.content


@pytest.mark.asyncio
async def test_shell_tool_dangerous_detection() -> None:
    """Dangerous commands should be flagged."""
    assert ShellTool.is_dangerous("rm -rf /")
    assert not ShellTool.is_dangerous("echo hello")


@pytest.mark.asyncio
async def test_shell_tool_stderr() -> None:
    """Shell tool should capture stderr and signal error on non-zero exit."""
    tool = ShellTool()
    result = await tool.execute({"command": "echo hello &2>&1; exit 1", "timeout": 5})
    assert result.is_error
    assert "[stderr]" in result.content or "hello" in result.content


@pytest.mark.asyncio
async def test_shell_tool_cwd() -> None:
    """Shell tool should respect the cwd argument."""
    tool = ShellTool()
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await tool.execute({"command": "pwd", "cwd": tmpdir, "timeout": 5})
        assert not result.is_error
        assert tmpdir in result.content


@pytest.mark.asyncio
async def test_shell_tool_empty_command() -> None:
    """Empty command should return an error."""
    tool = ShellTool()
    result = await tool.execute({"command": ""})
    assert result.is_error
    assert "No command provided" in result.content


@pytest.mark.asyncio
async def test_file_write_and_read(tmp_path: Path) -> None:
    """File write then read should round-trip content."""
    path = tmp_path / "test.txt"
    write_tool = FileWriteTool()
    read_tool = FileReadTool()

    result = await write_tool.execute({"path": str(path), "content": "hello world"})
    assert not result.is_error

    result = await read_tool.execute({"path": str(path)})
    assert not result.is_error
    assert "hello world" in result.content


@pytest.mark.asyncio
async def test_file_read_with_offset_limit(tmp_path: Path) -> None:
    """File read with offset/limit should return the correct slice."""
    path = tmp_path / "multi.txt"
    content = "\n".join(f"line {i}" for i in range(1, 21))
    path.write_text(content, encoding="utf-8")

    read_tool = FileReadTool()
    result = await read_tool.execute({"path": str(path), "offset": 5, "limit": 3})
    assert not result.is_error
    assert "line 5" in result.content
    assert "line 7" in result.content
    assert "line 8" not in result.content


@pytest.mark.asyncio
async def test_file_read_missing(tmp_path: Path) -> None:
    """Reading a missing file should return an error."""
    path = tmp_path / "missing.txt"
    read_tool = FileReadTool()
    result = await read_tool.execute({"path": str(path)})
    assert result.is_error
    assert "File not found" in result.content


@pytest.mark.asyncio
async def test_file_patch_basic(tmp_path: Path) -> None:
    """File patch should apply a unified diff correctly."""
    path = tmp_path / "patch_me.py"
    original = 'print("hello")\nprint("world")\n'
    path.write_text(original, encoding="utf-8")

    diff = (
        "--- patch_me.py\n"
        "+++ patch_me.py\n"
        "@@ -1,2 +1,2 @@\n"
        ' print("hello")\n'
        '-print("world")\n'
        '+print("sena")\n'
    )

    patch_tool = FilePatchTool()
    result = await patch_tool.execute({"path": str(path), "diff": diff})
    assert not result.is_error, result.content
    new_content = path.read_text(encoding="utf-8")
    assert 'print("sena")' in new_content
    assert 'print("world")' not in new_content


@pytest.mark.asyncio
async def test_file_patch_missing_file(tmp_path: Path) -> None:
    """Patching a missing file should return an error."""
    path = tmp_path / "missing.py"
    patch_tool = FilePatchTool()
    result = await patch_tool.execute({"path": str(path), "diff": "---"})
    assert result.is_error
    assert "File not found" in result.content


@pytest.mark.asyncio
async def test_git_tool_status() -> None:
    """Git tool should return status for a valid git repo."""
    import tempfile
    from pathlib import Path

    tool = GitTool()
    with tempfile.TemporaryDirectory() as tmpdir:
        proc = await asyncio.create_subprocess_exec(
            "git", "init",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir,
        )
        await proc.communicate()

        (Path(tmpdir) / "test.txt").write_text("hello", encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            "git", "add", "test.txt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir,
        )
        await proc.communicate()

        result = await tool.execute({"command": "status", "cwd": tmpdir})
        assert not result.is_error
        assert "test.txt" in result.content


@pytest.mark.asyncio
async def test_git_tool_disallowed() -> None:
    """Disallowed git commands should return an error."""
    tool = GitTool()
    result = await tool.execute({"command": "push origin main"})
    assert result.is_error
    assert "not in the allowed set" in result.content


@pytest.mark.asyncio
async def test_tool_registry() -> None:
    """Tool registry should register and dispatch tools."""
    registry = ToolRegistry()
    registry.register(ShellTool())
    registry.register(FileReadTool())

    assert len(registry.definitions()) == 2
    assert registry.get("shell") is not None
    assert registry.get("nonexistent") is None

    result = await registry.execute("shell", {"command": "echo registry", "timeout": 5})
    assert "registry" in result.content
