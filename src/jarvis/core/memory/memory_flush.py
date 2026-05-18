"""Memory flush before compaction (OpenClaw pattern).

When context usage exceeds SOFT_THRESHOLD, write critical conversation
state to disk before LLM summarization discards it. This preserves key
decisions, modified files, and task state that would otherwise be lost.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOFT_THRESHOLD_TOKENS = 4000  # flush when context usage exceeds this
MEMORY_DIR_NAME = "memory"    # subdirectory under .jarvis/


class MemoryFlushPolicy:
    """Decides whether a memory flush is needed before compaction."""

    def __init__(self, soft_threshold_tokens: int = SOFT_THRESHOLD_TOKENS) -> None:
        self.soft_threshold = soft_threshold_tokens
        self._last_flush_token_count = 0

    def should_flush(self, current_tokens: int) -> bool:
        """Return True if context has grown enough since last flush."""
        if current_tokens < self.soft_threshold:
            return False
        growth = current_tokens - self._last_flush_token_count
        return growth >= self.soft_threshold

    def record_flush(self, token_count: int) -> None:
        self._last_flush_token_count = token_count


class MemoryFlushExecutor:
    """Writes key context to .jarvis/memory/YYYY-MM-DD.md before compaction."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.memory_dir = self.repo_root / ".jarvis" / MEMORY_DIR_NAME

    def flush(
        self,
        *,
        token_count: int,
        active_task: dict[str, Any] | None = None,
        recent_decisions: list[str] | None = None,
        modified_files: list[str] | None = None,
    ) -> Path | None:
        """Write current state to a dated memory file. Returns path or None."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        memory_file = self.memory_dir / f"{today}.md"

        lines: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        lines.append(f"## Memory flush — {ts}")
        lines.append(f"(auto-saved before context compaction, {token_count} tokens in use)")
        lines.append("")

        if active_task:
            lines.append("### Active task")
            lines.append(f"- Goal: {active_task.get('goal', active_task.get('user_goal', 'unknown'))}")
            status = active_task.get("status", "")
            if status:
                lines.append(f"- Status: {status}")
            steps = active_task.get("steps") or []
            if steps:
                lines.append("- Steps:")
                for s in steps[-10:]:
                    lines.append(f"  - {s}")
            lines.append("")

        if recent_decisions:
            lines.append("### Key decisions")
            for d in recent_decisions[-10:]:
                lines.append(f"- {d}")
            lines.append("")

        if modified_files:
            lines.append("### Files modified")
            for f in modified_files[-20:]:
                lines.append(f"- `{f}`")
            lines.append("")

        content = "\n".join(lines).strip()
        # Return None if only the timestamp header would be written
        meaningful = [l for l in lines if l.strip() and not l.startswith("## Memory flush") and not l.startswith("(auto-saved")]
        if not meaningful:
            return None

        # Append to existing file to accumulate context across flushes
        existing = ""
        if memory_file.exists():
            existing = memory_file.read_text(encoding="utf-8", errors="replace").strip()
        if existing:
            content = existing + "\n\n" + content

        memory_file.write_text(content + "\n", encoding="utf-8")
        return memory_file
