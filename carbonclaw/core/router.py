"""Smart task routing for CarbonClaw.

Automatically selects the best model/provider based on task complexity,
carbon footprint, latency, and cost.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.core.models import Message

logger = structlog.get_logger(__name__)


class RoutingStrategy(Enum):
    """Strategies for model selection."""

    SUSTAINABILITY = "sustainability"  # Prioritize local models to save CO2
    LATENCY = "latency"               # Prioritize fastest response
    COST = "cost"                     # Prioritize cheapest
    BALANCED = "balanced"             # Mix of all


@dataclass
class ProviderStats:
    """Performance metrics for a provider."""

    name: str
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    request_count: int = 0
    is_local: bool = False
    is_healthy: bool = True
    last_checked: float = 0.0


class SmartRouter:
    """Routes tasks to the most appropriate provider/model."""

    def __init__(self, config: CarbonClawConfig):
        self.config = config
        self.stats: dict[str, ProviderStats] = {}
        self._init_stats()

    def _init_stats(self) -> None:
        """Initialize stats for enabled providers."""
        # Note: In a real app, these would be loaded from persistent telemetry
        providers = ["openai", "anthropic", "gemini", "ollama"]
        for p in providers:
            is_local = p == "ollama"
            self.stats[p] = ProviderStats(name=p, is_local=is_local)

    def update_metrics(self, provider: str, latency_ms: float, success: bool) -> None:
        """Update provider metrics using Exponential Moving Average (EMA)."""
        if provider not in self.stats:
            return

        s = self.stats[provider]
        s.request_count += 1
        
        # EMA for latency (alpha = 0.3)
        alpha = 0.3
        if s.avg_latency_ms == 0:
            s.avg_latency_ms = latency_ms
        else:
            s.avg_latency_ms = (alpha * latency_ms) + (1 - alpha) * s.avg_latency_ms

        # Simple error rate tracking
        error_val = 0.0 if success else 1.0
        s.error_rate = (alpha * error_val) + (1 - alpha) * s.error_rate
        
        if s.error_rate > 0.7 and s.request_count > 3:
            s.is_healthy = False
            s.last_checked = time.time()
        else:
            s.is_healthy = True

    def calculate_complexity(self, task: str, messages: list[Message] | None = None) -> float:
        """
        Estimate task complexity (0.0 to 1.0).
        
        Factors:
        - Message length
        - Keywords (refactor, architect, complex, etc.)
        - History depth
        """
        score = 0.2  # Base
        
        # Length factor
        total_len = len(task)
        if messages:
            total_len += sum(len(m.content or "") for m in messages)
        
        if total_len > 2000:
            score += 0.4
        elif total_len > 500:
            score += 0.2

        # Keyword factor
        complex_keywords = ["refactor", "architect", "optimize", "debug", "deep", "analyze"]
        if any(kw in task.lower() for kw in complex_keywords):
            score += 0.3
            
        return min(1.0, score)

    def route(
        self, 
        task: str, 
        messages: list[Message] | None = None,
        strategy: RoutingStrategy = RoutingStrategy.SUSTAINABILITY
    ) -> tuple[str, str]:
        """
        Decide which (provider, model) to use.
        
        Returns:
            Tuple of (provider_name, model_id)
        """
        complexity = self.calculate_complexity(task, messages)
        
        # Filter healthy providers
        available = [s for s in self.stats.values() if s.is_healthy]
        if not available:
            # Fallback to default config if everything is "unhealthy"
            return self.config.default_provider, self.config.default_model or "llama3.2"

        # SUSTAINABILITY Strategy:
        # If complexity is low (< 0.5), FORCE local model (Ollama)
        if strategy == RoutingStrategy.SUSTAINABILITY:
            if complexity < 0.5 and "ollama" in self.stats and self.stats["ollama"].is_healthy:
                return "ollama", self.config.default_model or "llama3.2"
            
            # For complex tasks, pick based on configuration preference but prefer high-quality
            # Here we might pick Anthropic or OpenAI
            return self.config.default_provider, self.config.default_model or "gpt-4o"

        # BALANCED Strategy: Similar to OpenClaude scoring
        def get_score(s: ProviderStats) -> float:
            latency_factor = s.avg_latency_ms / 1000.0
            # Carbon/Cost factor: local = 0, cloud = 1.0
            sustainability_factor = 0.0 if s.is_local else 1.0
            error_penalty = s.error_rate * 500.0
            
            return (latency_factor * 0.2) + (sustainability_factor * 0.8) + error_penalty

        best_provider = min(available, key=get_score)
        
        # Model selection within provider
        model = self.config.default_model or "llama3.2"
        if not best_provider.is_local and complexity > 0.6:
            # Switch to 'pro' model for complex cloud tasks
            if best_provider.name == "anthropic":
                model = "claude-3-5-sonnet-latest"
            elif best_provider.name == "openai":
                model = "gpt-4o"
        
        return best_provider.name, model
