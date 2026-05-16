"""Tests for the slash command system."""

from __future__ import annotations

import pytest
from sena.cli.slash import SlashRegistry, SlashResult, _cmd_clear, _cmd_compact, _cmd_cost
from sena.core.models import Message


def test_registry_has_default_commands() -> None:
    """Built-in commands are registered on construction."""
    registry = SlashRegistry()
    assert "clear" in {c.name for c in registry._commands.values()}
    assert "compact" in {c.name for c in registry._commands.values()}
    assert "help" in {c.name for c in registry._commands.values()}
    assert "debug" in {c.name for c in registry._commands.values()}
    assert "model" in {c.name for c in registry._commands.values()}
    assert "cost" in {c.name for c in registry._commands.values()}


@pytest.mark.asyncio
async def test_dispatch_unknown_command_returns_none() -> None:
    """Non-slash input and unknown commands return None."""
    registry = SlashRegistry()
    messages = [Message(role="system", content="sys")]
    assert await registry.dispatch(messages, "not a slash command") is None
    assert await registry.dispatch(messages, "/nonexistent") is None


@pytest.mark.asyncio
async def test_dispatch_clear_keeps_system() -> None:
    """/clear preserves the system message."""
    registry = SlashRegistry()
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi"),
    ]
    result = await registry.dispatch(messages, "/clear")
    assert isinstance(result, SlashResult)
    assert result.messages is not None
    assert len(result.messages) == 1
    assert result.messages[0].role == "system"
    assert "cleared" in result.output.lower()


@pytest.mark.asyncio
async def test_dispatch_clear_alias_cls() -> None:
    """/cls is an alias for /clear."""
    registry = SlashRegistry()
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="hello"),
    ]
    result = await registry.dispatch(messages, "/cls")
    assert isinstance(result, SlashResult)
    assert result.messages is not None
    assert len(result.messages) == 1


@pytest.mark.asyncio
async def test_dispatch_compact() -> None:
    """/compact replaces history with a summary request."""
    registry = SlashRegistry()
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi"),
    ]
    result = await registry.dispatch(messages, "/compact")
    assert isinstance(result, SlashResult)
    assert result.messages is not None
    assert len(result.messages) == 2
    assert result.messages[0].role == "system"
    assert result.messages[1].role == "user"
    assert result.messages[1].content is not None
    assert "summary" in result.messages[1].content.lower()


@pytest.mark.asyncio
async def test_dispatch_help_returns_table() -> None:
    """/help returns a Rich Table renderable."""
    registry = SlashRegistry()
    messages = [Message(role="system", content="sys")]
    result = await registry.dispatch(messages, "/help")
    assert isinstance(result, SlashResult)
    from rich.table import Table

    assert isinstance(result.output, Table)


@pytest.mark.asyncio
async def test_dispatch_help_aliases() -> None:
    """/h and /? are aliases for /help."""
    registry = SlashRegistry()
    messages = [Message(role="system", content="sys")]
    for alias in ("/h", "/?"):
        result = await registry.dispatch(messages, alias)
        assert isinstance(result, SlashResult)


@pytest.mark.asyncio
async def test_dispatch_debug() -> None:
    """/debug prints a status message."""
    registry = SlashRegistry()
    messages = [Message(role="system", content="sys")]
    result = await registry.dispatch(messages, "/debug")
    assert isinstance(result, SlashResult)
    assert "debug" in result.output.lower()


@pytest.mark.asyncio
async def test_dispatch_cost() -> None:
    """/cost reports approximate token usage."""
    registry = SlashRegistry()
    messages = [Message(role="system", content="sys")]
    result = await registry.dispatch(messages, "/cost")
    assert isinstance(result, SlashResult)
    assert "tokens" in result.output.lower()


@pytest.mark.asyncio
async def test_custom_command() -> None:
    """User-registered commands are dispatched correctly."""
    registry = SlashRegistry()

    async def _custom_handler(_msgs: list[Message], args: str, _reg: SlashRegistry) -> SlashResult:
        return SlashResult(output=f"custom: {args}")

    registry.register("custom", "A custom command.", _custom_handler)
    messages = [Message(role="system", content="sys")]
    result = await registry.dispatch(messages, "/custom hello")
    assert isinstance(result, SlashResult)
    assert result.output == "custom: hello"


@pytest.mark.asyncio
async def test_custom_command_aliases() -> None:
    """Aliases for custom commands work as expected."""
    registry = SlashRegistry()

    async def _custom_handler(_msgs: list[Message], args: str, _reg: SlashRegistry) -> SlashResult:
        return SlashResult(output=f"custom: {args}")

    registry.register("custom", "A custom command.", _custom_handler, aliases=("c", "cm"))
    messages = [Message(role="system", content="sys")]
    for alias in ("/c", "/cm"):
        result = await registry.dispatch(messages, alias)
        assert isinstance(result, SlashResult)
        assert result.output == "custom: "


@pytest.mark.asyncio
async def test_cmd_clear_no_system() -> None:
    """Clear with no system message leaves an empty list."""
    messages = [Message(role="user", content="hello")]
    result = await _cmd_clear(messages, "", SlashRegistry())
    assert result.messages == []


@pytest.mark.asyncio
async def test_cmd_compact_no_system() -> None:
    """Compact with no system message adds a user summary request."""
    messages = [Message(role="user", content="hello")]
    result = await _cmd_compact(messages, "", SlashRegistry())
    assert result.messages is not None
    assert len(result.messages) == 1
    assert result.messages[0].role == "user"


@pytest.mark.asyncio
async def test_cmd_cost_empty() -> None:
    """Cost on an empty session still reports tokens."""
    messages = [Message(role="system", content="sys")]
    result = await _cmd_cost(messages, "", SlashRegistry())
    assert "tokens" in result.output.lower()
