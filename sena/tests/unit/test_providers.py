"""Unit tests for provider message normalization."""

from __future__ import annotations

import json

from sena.core.models import Message, ToolCall
from sena.providers.base import _message_to_anthropic, _message_to_openai


def test_message_to_openai_text() -> None:
    msg = Message(role="user", content="hello")
    out = _message_to_openai(msg)
    assert out == {"role": "user", "content": "hello"}


def test_message_to_openai_tool_call() -> None:
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="1", name="shell", arguments={"command": "ls"})],
    )
    out = _message_to_openai(msg)
    assert out["role"] == "assistant"
    assert len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["function"]["name"] == "shell"
    assert json.loads(out["tool_calls"][0]["function"]["arguments"]) == {"command": "ls"}


def test_message_to_anthropic_system() -> None:
    msg = Message(role="system", content="You are Sena.")
    out = _message_to_anthropic(msg)
    assert out == {"role": "system", "content": "You are Sena."}


def test_message_to_anthropic_tool_result() -> None:
    msg = Message(role="tool", content="output", tool_call_id="tc1", name="shell")
    out = _message_to_anthropic(msg)
    assert out["role"] == "user"
    assert out["content"][0]["type"] == "tool_result"
