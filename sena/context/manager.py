"""Context management: token budgeting, summarization, sliding window."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

from sena.core.models import Message, CompletionRequest
from sena.core.base import BaseProvider

logger = structlog.get_logger()


@dataclass
class TokenBudget:
    """Token budget for a conversation turn."""

    max_total: int = 128_000
    max_completion: int = 4096
    reserve_tools: int = 2000
    reserve_system: int = 500
    current_usage: int = 0

    def available_for_context(self) -> int:
        return self.max_total - self.max_completion - self.reserve_tools - self.reserve_system - self.current_usage


class TokenCounter:
    """Estimate token counts using provider-native or heuristic counting."""

    # Rough heuristic: ~4 chars per token for English text
    CHARS_PER_TOKEN = 4

    @classmethod
    def estimate(cls, text: str) -> int:
        return max(1, len(text) // cls.CHARS_PER_TOKEN)

    @classmethod
    def count_messages(cls, messages: list[Message]) -> int:
        total = 0
        for msg in messages:
            text = msg.content or ""
            total += cls.estimate(text)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += cls.estimate(tc.name)
                    total += cls.estimate(json.dumps(tc.arguments))
        return total


class ConversationSummarizer:
    """Summarize conversation history when approaching token limits."""

    def __init__(self, provider: BaseProvider, model: str | None = None) -> None:
        self.provider = provider
        self.model = model

    async def summarize(self, messages: list[Message], max_tokens: int = 256) -> str:
        """Generate a concise summary of the conversation so far."""
        transcript = "\n".join(
            f"{m.role}: {m.content or '[tool call]' }" for m in messages
        )
        prompt = (
            "Summarize the following conversation concisely. "
            "Preserve key decisions, facts, and action items:\n\n"
            f"{transcript}\n\nSummary:"
        )
        from sena.core.models import CompletionRequest, Message
        response = await self.provider.complete(
            CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                model=self.model or "",
                max_tokens=max_tokens,
                stream=False,
            )
        )
        return response.message.content or ""


class SlidingWindow:
    """Keep only the most recent N messages within a token budget."""

    def __init__(
        self,
        budget: TokenBudget,
        keep_system: bool = True,
        keep_first_n: int = 2,
    ) -> None:
        self.budget = budget
        self.keep_system = keep_system
        self.keep_first_n = keep_first_n

    def trim(self, messages: list[Message]) -> list[Message]:
        """Trim messages to fit within the token budget."""
        total = TokenCounter.count_messages(messages)
        if total <= self.budget.available_for_context():
            return messages

        preserved: list[Message] = []
        rest: list[Message] = []

        for i, msg in enumerate(messages):
            if self.keep_system and msg.role == "system":
                preserved.append(msg)
            elif i < self.keep_first_n:
                preserved.append(msg)
            else:
                rest.append(msg)

        # Drop oldest messages from rest until budget fits
        while rest and (
            TokenCounter.count_messages(preserved + rest)
            > self.budget.available_for_context()
        ):
            rest.pop(0)

        return preserved + rest


class ContextManager:
    """Orchestrates token budgeting, summarization, and sliding window trimming."""

    def __init__(
        self,
        provider: BaseProvider,
        budget: TokenBudget | None = None,
        model: str | None = None,
        auto_summarize: bool = True,
    ) -> None:
        self.provider = provider
        self.budget = budget or TokenBudget()
        self.model = model
        self.auto_summarize = auto_summarize
        self.summarizer = ConversationSummarizer(provider, model)
        self.window = SlidingWindow(self.budget)
        self._summary: str | None = None

    async def prepare(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> list[Message]:
        """Prepare messages for a completion request within budget."""
        total = TokenCounter.count_messages(messages)
        available = self.budget.available_for_context()

        if total <= available:
            logger.debug("context.within_budget", total=total, available=available)
            return messages

        logger.info("context.budget_exceeded", total=total, available=available)

        # Try sliding window first
        trimmed = self.window.trim(messages)
        if TokenCounter.count_messages(trimmed) <= available:
            logger.info("context.trimmed_via_window", before=len(messages), after=len(trimmed))
            return trimmed

        # Fall back to summarization
        if self.auto_summarize:
            self._summary = await self.summarizer.summarize(messages)
            summary_msg = Message(role="system", content=f"Summary of prior conversation: {self._summary}")
            # Keep only system + last user/assistant exchange
            preserved = [m for m in messages if m.role == "system"]
            preserved.append(summary_msg)
            # Append last 2 non-system messages
            for m in messages[-2:]:
                if m.role != "system":
                    preserved.append(m)
            logger.info("context.summarized", summary_length=len(self._summary))
            return preserved

        return trimmed

    def budget_status(self, messages: list[Message]) -> dict[str, int]:
        total = TokenCounter.count_messages(messages)
        return {
            "total_tokens": total,
            "available": self.budget.available_for_context(),
            "max_total": self.budget.max_total,
            "remaining": self.budget.available_for_context() - total,
        }
