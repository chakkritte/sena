"""Unit tests for context management."""

from __future__ import annotations

import pytest

from sena.context.manager import TokenBudget, TokenCounter, SlidingWindow
from sena.core.models import Message


def test_token_counter_estimate() -> None:
    assert TokenCounter.estimate("hello world") == 2  # 11 chars / 4 = 2
    assert TokenCounter.estimate("") == 1  # minimum 1


def test_token_counter_messages() -> None:
    msgs = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hello!"),
        Message(role="assistant", content="Hi there."),
    ]
    total = TokenCounter.count_messages(msgs)
    assert total > 0


def test_token_budget() -> None:
    budget = TokenBudget(max_total=1000, max_completion=100, reserve_tools=50)
    assert budget.available_for_context() == 1000 - 100 - 50 - 500 - 0


def test_sliding_window_no_trim() -> None:
    budget = TokenBudget(max_total=100_000)
    window = SlidingWindow(budget)
    msgs = [Message(role="user", content="hello")]
    result = window.trim(msgs)
    assert len(result) == 1


def test_sliding_window_trims() -> None:
    budget = TokenBudget(max_total=100)
    window = SlidingWindow(budget, keep_first_n=1)
    msgs = [
        Message(role="system", content="system prompt"),
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi" * 500),  # large
    ]
    result = window.trim(msgs)
    # Should drop the oversized message
    assert len(result) <= 2
