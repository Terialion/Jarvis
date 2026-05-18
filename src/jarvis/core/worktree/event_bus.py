"""Append-only lifecycle event log for worktree operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class EventBus:
    """JSONL event log for worktree lifecycle observability."""

    def __init__(self, event_log_path: Path) -> None:
        self.path = Path(event_log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event: str,
        task: dict[str, Any] | None = None,
        worktree: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        line: dict[str, Any] = {"event": event, "ts": time.time()}
        if task:
            line["task"] = task
        if worktree:
            line["worktree"] = worktree
        if error:
            line["error"] = error
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[dict[str, Any]] = []
        for line in lines[-max(1, limit):]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries
