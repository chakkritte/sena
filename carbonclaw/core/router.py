"""Smart task routing for CarbonClaw.

Automatically selects the best model/provider based on task complexity,
carbon footprint, latency, and cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from carbonclaw.core.models import Message, TaskType
from carbonclaw.routing.classifier import classify_task

if TYPE_CHECKING:
    from carbonclaw.config.settings import CarbonClawConfig

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
    """Routes tasks to the most appropriate provider/model based on type and metrics."""

    def __init__(
        self,
        config: CarbonClawConfig,
        strategic_adjustments: list[dict[str, Any]] | None = None,
    ):
        """Initialize the SmartRouter."""
        self.config = config
        self.stats: dict[str, ProviderStats] = {}
        self._init_stats()
        self.strategic_adjustments = strategic_adjustments or []

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
        """Estimate task complexity (0.0 to 1.0)."""
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
            score += 0.5

        return min(1.0, score)

    def route(
        self,
        task: str,
        messages: list[Message] | None = None,
        strategy: RoutingStrategy = RoutingStrategy.SUSTAINABILITY
    ) -> tuple[str, str, TaskType]:
        """Decide which (provider, model, task_type) to use."""
        task_type = classify_task(task)
        complexity = self.calculate_complexity(task, messages)

        # Filter healthy providers
        available = [s for s in self.stats.values() if s.is_healthy]
        if not available:
            return self.config.default_provider, self.config.default_model or "llama3.2", task_type

        # Determine the target model for this task type from config
        task_model = self.config.routing_models.get(task_type.value)

        # Check Carbon Budget constraints (Feature 2)
        budget_g = self.config.carbon_budget
        if budget_g is not None:
            from carbonclaw.telemetry.carbon import CarbonStore
            store = CarbonStore()
            curr_emissions_g = store.total_emissions() * 1000.0

            if curr_emissions_g >= budget_g:
                # Carbon budget exhausted: force local Ollama to save further cloud CO2 emissions
                logger.info(
                    "router.carbon_budget_exhausted", current=curr_emissions_g, budget=budget_g
                )
                if "ollama" in self.stats and self.stats["ollama"].is_healthy:
                    model = task_model or self.config.default_model or "llama3.2"
                    return "ollama", model, task_type
            elif curr_emissions_g >= budget_g * 0.7:
                # Carbon budget low (> 70% used): downgrade medium tasks to local models
                logger.info("router.carbon_budget_low", current=curr_emissions_g, budget=budget_g)
                if (
                    complexity < 0.8
                    and "ollama" in self.stats
                    and self.stats["ollama"].is_healthy
                ):
                    model = task_model or self.config.default_model or "llama3.2"
                    return "ollama", model, task_type

        # Apply Strategic Adjustments
        strategy_override_provider = None
        strategy_override_model = None
        for adj in self.strategic_adjustments:
            if adj.get("target_task_type") == task_type.value:
                # Basic condition parser
                cond = str(adj.get("condition", ""))
                match = True
                if "complexity >" in cond:
                    try:
                        thresh = float(cond.split(">")[1].strip())
                        match = complexity > thresh
                    except ValueError:
                        pass

                if match:
                    action = adj.get("action", "")
                    if action == "prefer_cloud":
                        strategy_override_provider = self.config.default_provider
                        strategy_override_model = "gpt-4o"  # or other robust cloud model
                    elif action.startswith("force_"):
                        strategy_override_provider = action.replace("force_", "")
                    break # Apply first matched strategy

        if strategy_override_provider:
            # Re-evaluate model if provider changed
            if not strategy_override_model:
                 strategy_override_model = self.config.default_model or "llama3.2"
            return strategy_override_provider, strategy_override_model, task_type

        # 1. SUSTAINABILITY Strategy:
        if strategy == RoutingStrategy.SUSTAINABILITY:
            # If complexity is high, pick cloud to ensure quality
            if complexity >= 0.7:
                model = self.config.default_model or "gpt-4o"
                return self.config.default_provider, model, task_type

            # Prefer local for simple/medium tasks
            if "ollama" in self.stats and self.stats["ollama"].is_healthy:
                model = task_model or self.config.default_model or "llama3.2"
                return "ollama", model, task_type

            # Fallback to cloud if Ollama unhealthy
            return self.config.default_provider, self.config.default_model or "gpt-4o", task_type

        # 2. BALANCED Strategy: Similar to OpenClaude scoring
        def get_score(s: ProviderStats) -> float:
            latency_factor = s.avg_latency_ms / 1000.0
            # Carbon/Cost factor: local = 0, cloud = 1.0
            sustainability_factor = 0.0 if s.is_local else 1.0
            error_penalty = s.error_rate * 500.0

            return (latency_factor * 0.2) + (sustainability_factor * 0.8) + error_penalty

        best_provider = min(available, key=get_score)

        # Model selection within provider
        model = task_model or self.config.default_model or "llama3.2"

        # If cloud and very complex, switch to 'pro' model
        if not best_provider.is_local and complexity > 0.8:
            if best_provider.name == "anthropic":
                model = "claude-3-5-sonnet-latest"
            elif best_provider.name == "openai":
                model = "gpt-4o"

        return best_provider.name, model, task_type
