"""Session telemetry: track token usage and costs per provider/model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir


@dataclass
class UsageRecord:
    """A single LLM request usage record."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    timestamp: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class TelemetryStore:
    """Persist and query usage records across sessions."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            data_dir = Path(user_data_dir("carbonclaw", "carbonclaw"))
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "telemetry.jsonl"
        self._path = path

    def record(self, entry: UsageRecord) -> None:
        """Append a usage record."""
        import datetime

        if not entry.timestamp:
            entry.timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        line = json.dumps(
            {
                "provider": entry.provider,
                "model": entry.model,
                "prompt_tokens": entry.prompt_tokens,
                "completion_tokens": entry.completion_tokens,
                "total_tokens": entry.total_tokens,
                "timestamp": entry.timestamp,
            }
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def records(self) -> list[UsageRecord]:
        """Load all records."""
        results: list[UsageRecord] = []
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
                        UsageRecord(
                            provider=data.get("provider", ""),
                            model=data.get("model", ""),
                            prompt_tokens=data.get("prompt_tokens", 0),
                            completion_tokens=data.get("completion_tokens", 0),
                            timestamp=data.get("timestamp", ""),
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    continue
        return results

    def summary(self) -> dict[str, Any]:
        """Return aggregated usage statistics with cost estimation."""
        records = self.records()
        total_prompt = sum(r.prompt_tokens for r in records)
        total_completion = sum(r.completion_tokens for r in records)
        
        # Simple cost map (USD per 1M tokens) - Examples
        # In production, this should be a dynamic config or updated regularly
        COST_MAP = {
            "openai/gpt-4o-mini": (0.15, 0.60),
            "openai/gpt-4o": (2.50, 10.0),
            "anthropic/claude-3-5-sonnet-latest": (3.0, 15.0),
            "anthropic/claude-3-5-haiku-latest": (0.25, 1.25),
            "gemini/gemini-1.5-flash": (0.075, 0.30),
            "ollama": (0.0, 0.0),
        }

        total_cost = 0.0
        by_model: dict[str, dict[str, Any]] = {}
        for r in records:
            key = f"{r.provider}/{r.model}"
            # Check for generic provider cost if specific model not found
            prices = COST_MAP.get(key, COST_MAP.get(r.provider, (0.0, 0.0)))
            
            p_cost = (r.prompt_tokens / 1_000_000) * prices[0]
            c_cost = (r.completion_tokens / 1_000_000) * prices[1]
            total_cost += p_cost + c_cost
            
            by_model.setdefault(key, {"prompt": 0, "completion": 0, "requests": 0, "cost": 0.0})
            by_model[key]["prompt"] += r.prompt_tokens
            by_model[key]["completion"] += r.completion_tokens
            by_model[key]["requests"] += 1
            by_model[key]["cost"] += p_cost + c_cost

        return {
            "total_requests": len(records),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_cost_usd": round(total_cost, 6),
            "by_model": by_model,
        }

    def clear(self) -> None:
        """Delete all telemetry records."""
        if self._path.exists():
            self._path.unlink()
