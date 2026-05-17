"""Carbon emission tracking for CarbonClaw using CodeCarbon."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

import structlog

try:
    from codecarbon import EmissionsTracker
    _CODECARBON_AVAILABLE = True
except ImportError:
    _CODECARBON_AVAILABLE = False

logger = structlog.get_logger(__name__)


class CarbonTracker:
    """Wrapper for CodeCarbon EmissionsTracker."""

    def __init__(self, project_name: str = "carbonclaw", enabled: bool = True):
        self.enabled = enabled and _CODECARBON_AVAILABLE
        self.project_name = project_name
        self._tracker: EmissionsTracker | None = None
        self._last_emissions: float = 0.0

    def start(self) -> None:
        """Start tracking emissions."""
        if not self.enabled:
            return

        try:
            # Silence codecarbon's own logging to avoid clutter
            logging.getLogger("codecarbon").setLevel(logging.ERROR)
            self._tracker = EmissionsTracker(
                project_name=self.project_name,
                measure_power_secs=15,
                save_to_file=False,  # We handle storage via telemetry/store
                log_level="error",
            )
            self._tracker.start()
        except Exception as e:
            logger.warning("carbon.tracker.start_failed", error=str(e))
            self.enabled = False

    def stop(self) -> float:
        """Stop tracking and return emissions in kg CO2."""
        if not self.enabled or not self._tracker:
            return 0.0

        try:
            emissions = self._tracker.stop()
            self._last_emissions = float(emissions) if emissions is not None else 0.0
            return self._last_emissions
        except Exception as e:
            logger.warning("carbon.tracker.stop_failed", error=str(e))
            return 0.0
        finally:
            self._tracker = None

    @property
    def last_emissions(self) -> float:
        """Get the emissions from the last tracking period."""
        return self._last_emissions


@contextlib.contextmanager
def track_carbon(name: str, enabled: bool = True) -> Iterator[CarbonTracker]:
    """Context manager for carbon tracking."""
    tracker = CarbonTracker(project_name=name, enabled=enabled)
    tracker.start()
    try:
        yield tracker
    finally:
        tracker.stop()


def get_greener_recommendation(task: str, complexity_score: float) -> str | None:
    """
    Recommend a greener alternative if the task is simple.
    
    Args:
        task: The task description.
        complexity_score: A score from 0 to 1 representing task complexity.
        
    Returns:
        A recommendation string or None if no recommendation is needed.
    """
    # Simple heuristic for now: if complexity is low, suggest local model
    if complexity_score < 0.3:
        return (
            "🌱 This task seems simple. Consider using a local LLM (e.g., Llama 3.2 via Ollama) "
            "to reduce carbon footprint from network and cloud compute."
        )
    return None
