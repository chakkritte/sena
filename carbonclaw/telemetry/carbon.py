"""Carbon emission tracking for CarbonClaw using CodeCarbon."""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import structlog
from platformdirs import user_data_dir

try:
    from codecarbon import EmissionsTracker
    _CODECARBON_AVAILABLE = True
except ImportError:
    _CODECARBON_AVAILABLE = False

logger = structlog.get_logger(__name__)


@dataclass
class CarbonRecord:
    """A single carbon emission record."""

    project_name: str
    emissions: float  # kg CO2
    timestamp: str = ""


class CarbonStore:
    """Persist and query carbon emission records."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            data_dir = Path(user_data_dir("carbonclaw", "carbonclaw"))
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "emissions.jsonl"
        self._path = path

    def record(self, entry: CarbonRecord) -> None:
        """Append a carbon emission record."""
        if not entry.timestamp:
            entry.timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        line = json.dumps(
            {
                "project_name": entry.project_name,
                "emissions": entry.emissions,
                "timestamp": entry.timestamp,
            }
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def records(self) -> list[CarbonRecord]:
        """Load all records."""
        results: list[CarbonRecord] = []
        if not self._path.exists():
            return results
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    results.append(
                        CarbonRecord(
                            project_name=data.get("project_name", ""),
                            emissions=data.get("emissions", 0.0),
                            timestamp=data.get("timestamp", ""),
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    continue
        return results

    def total_emissions(self) -> float:
        """Return the total emissions across all records in kg CO2."""
        return sum(r.emissions for r in self.records())

    def clear(self) -> None:
        """Delete all emission records."""
        if self._path.exists():
            self._path.unlink()


class CarbonTracker:
    """Wrapper for CodeCarbon EmissionsTracker."""

    def __init__(self, project_name: str = "carbonclaw", enabled: bool = True):
        self.enabled = enabled and _CODECARBON_AVAILABLE
        self.project_name = project_name
        self._tracker: EmissionsTracker | None = None
        self._last_emissions: float = 0.0
        self._store = CarbonStore()

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
                save_to_file=False,  # We handle storage via CarbonStore
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

            # Persist the result
            if self._last_emissions > 0:
                self._store.record(CarbonRecord(
                    project_name=self.project_name,
                    emissions=self._last_emissions
                ))

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
    """Recommend a greener alternative if the task is simple.
    
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


def parse_carbon_budget(budget: str | float | int | None) -> float | None:
    """Parse a carbon budget string (e.g. '5g', '12mg', '1kg') into a float value in grams.
    
    Returns None if budget is None or invalid.
    """
    if budget is None:
        return None
    if isinstance(budget, (int, float)):
        return float(budget)

    s = str(budget).strip().lower()
    if not s:
        return None

    try:
        if s.endswith("mg"):
            return float(s[:-2].strip()) / 1000.0
        elif s.endswith("kg"):
            return float(s[:-2].strip()) * 1000.0
        elif s.endswith("g"):
            return float(s[:-1].strip())
        else:
            return float(s)
    except ValueError:
        logger.warning("carbon.parse_budget_failed", budget=budget)
        return None

