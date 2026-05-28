"""Prompt Efficiency Optimizer and Compressor for CarbonClaw."""

from __future__ import annotations

import re


class PromptOptimizer:
    """Silently rewrites and compresses prompts to reduce token usage and CO2 emissions."""

    FILLER_PATTERNS = [
        r"\b(?:please|kindly|could you|would you mind|can you help me to|help me to)\b",
        r"\b(?:write a script to|create a program to|implement a function that)\b",
        r"\b(?:make sure that|take care to|be careful to|ensure that)\b",
        r"\b(?:in order to|with the goal of)\b",
    ]

    def __init__(self, enabled: bool = True) -> None:
        """Initialize the PromptOptimizer."""
        self.enabled = enabled

    def optimize(self, prompt: str) -> tuple[str, int]:
        """
        Compress the input prompt text by stripping filler phrases, redundant whitespaces, and punctuation.
        
        Returns:
            A tuple of (optimized_prompt, saved_tokens_count)
        """
        if not self.enabled or not prompt:
            return prompt, 0

        original_len = len(prompt)
        compressed = prompt

        # 1. Strip standard conversational filler phrases case-insensitively
        for pattern in self.FILLER_PATTERNS:
            compressed = re.sub(pattern, "", compressed, flags=re.IGNORECASE)

        # 2. Compress consecutive spaces and newlines
        compressed = re.sub(r"[ \t]+", " ", compressed)
        compressed = re.sub(r"\n{3,}", "\n\n", compressed)

        # Trim leading/trailing whitespace
        compressed = compressed.strip()

        # 3. Calculate saved tokens (rough heuristic: ~4 chars per token)
        chars_saved = max(0, original_len - len(compressed))
        saved_tokens = chars_saved // 4

        # If compression is minimal (< 3 tokens saved), keep original to preserve intent
        if saved_tokens < 3:
            return prompt, 0

        return compressed, saved_tokens
