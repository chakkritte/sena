"""Unit tests for DocsAgent, AST auditing, and docstring injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from carbonclaw.agents.docs import DocsAgent
from carbonclaw.cli.doc_cmd import get_git_modified_files, inject_docstring
from carbonclaw.core.models import CompletionResponse, Message


@pytest.fixture
def mock_provider() -> AsyncMock:
    """Create a mock LLM provider returning a docstring."""
    provider = AsyncMock()
    # Mock LLM response
    response_msg = Message(role="assistant", content='"""This is a mock docstring."""')
    provider.complete.return_value = CompletionResponse(
        message=response_msg,
        model="mock-model",
    )
    return provider


def test_inject_docstring(tmp_path: Path) -> None:
    """Test that docstring injection correctly places the docstring and preserves indent."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def hello_world():\n    print('hello')\n\nclass MyClass:\n    pass\n",
        encoding="utf-8"
    )

    # Inject docstring for hello_world
    success = inject_docstring(str(file_path), "hello_world", '"""Say hello."""')
    assert success is True

    content = file_path.read_text(encoding="utf-8")
    assert '    """Say hello."""' in content

    # Inject docstring for MyClass
    success_class = inject_docstring(str(file_path), "MyClass", '"""A mock class."""')
    assert success_class is True

    content_after = file_path.read_text(encoding="utf-8")
    assert '    """A mock class."""' in content_after


@pytest.mark.asyncio
async def test_audit_docstrings(tmp_path: Path, mock_provider: AsyncMock) -> None:
    """Test that DocsAgent correctly audits functions/classes missing docstrings."""
    file_path = tmp_path / "audit_test.py"
    file_path.write_text(
        '"""Module docstring."""\n'
        'def documented_fn():\n'
        '    """This function has a docstring."""\n'
        '    return 42\n'
        '\n'
        'def undocumented_fn(x):\n'
        '    return x * 2\n'
        '\n'
        'class UndocumentedClass:\n'
        '    def method_one(self):\n'
        '        pass\n',
        encoding="utf-8"
    )

    agent = DocsAgent(
        provider=mock_provider,
        tools=[],
        memory=AsyncMock(),
        model="mock-model"
    )

    missing = await agent.audit_docstrings(str(file_path))

    # Assert missing elements are detected (undocumented_fn and UndocumentedClass)
    names = {item["name"] for item in missing}
    assert "undocumented_fn" in names
    assert "UndocumentedClass" in names
    assert "documented_fn" not in names


@pytest.mark.asyncio
async def test_generate_docstring(mock_provider: AsyncMock) -> None:
    """Test that DocsAgent correctly invokes completion and formats the docstring."""
    agent = DocsAgent(
        provider=mock_provider,
        tools=[],
        memory=AsyncMock(),
        model="mock-model"
    )

    doc = await agent.generate_docstring("undocumented_fn", "def undocumented_fn(): pass")
    assert doc == '"""This is a mock docstring."""'
    assert mock_provider.complete.called


def test_get_git_modified_files() -> None:
    """Verify that get_git_modified_files returns a list even if git is not initialized."""
    files = get_git_modified_files()
    assert isinstance(files, list)
