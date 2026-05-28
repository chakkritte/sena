"""Unit tests for the Prompt Efficiency Optimizer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from carbonclaw.context.manager import ContextManager
from carbonclaw.context.optimizer import PromptOptimizer
from carbonclaw.core.models import Message


def test_prompt_optimizer_fluff_removal() -> None:
    """Test that filler words and courtesies are correctly stripped."""
    optimizer = PromptOptimizer(enabled=True)

    # 1. Polite filler phrasing
    raw = "Please could you kindly write a script to refactor this module?"
    opt, saved = optimizer.optimize(raw)
    assert saved > 0
    assert "please" not in opt.lower()
    assert "kindly" not in opt.lower()
    assert "could you" not in opt.lower()
    assert opt.strip() == "refactor this module?"

    # 2. Minimal savings preservation
    short = "hello"
    opt_short, saved_short = optimizer.optimize(short)
    assert saved_short == 0
    assert opt_short == "hello"


def test_prompt_optimizer_spacing() -> None:
    """Test compressing consecutive spaces and newlines."""
    optimizer = PromptOptimizer(enabled=True)

    raw = "Refactor this                 module \n\n\n\n\n\n\n\n\n\n\n\n now."
    opt, saved = optimizer.optimize(raw)
    assert saved > 0
    assert "\n\n\n" not in opt
    assert "   " not in opt


@pytest.mark.asyncio
async def test_context_manager_prompt_integration() -> None:
    """Test that ContextManager.prepare automatically triggers optimizer on user roles."""
    provider = MagicMock()
    ctx_mgr = ContextManager(provider=provider)

    messages = [
        Message(role="system", content="System prompt instructions."),
        Message(role="user", content="Could you kindly check if this file exists, please?"),
    ]

    prepared = await ctx_mgr.prepare(messages)
    assert len(prepared) == 2
    assert "check if this file exists" in prepared[1].content
    assert "kindly" not in prepared[1].content
