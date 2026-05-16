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
            data_dir = Path(user_data_dir("sena", "sena"))
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
        """Return aggregated usage statistics."""
        records = self.records()
        total_prompt = sum(r.prompt_tokens for r in records)
        total_completion = sum(r.completion_tokens for r in records)
        by_model: dict[str, dict[str, int]] = {}
        for r in records:
            key = f"{r.provider}/{r.model}"
            by_model.setdefault(key, {"prompt": 0, "completion": 0, "requests": 0})
            by_model[key]["prompt"] += r.prompt_tokens
            by_model[key]["completion"] += r.completion_tokens
            by_model[key]["requests"] += 1

        return {
            "total_requests": len(records),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "by_model": by_model,
        }

    def clear(self) -> None:
        """Delete all telemetry records."""
        if self._path.exists():
            self._path.unlink()
