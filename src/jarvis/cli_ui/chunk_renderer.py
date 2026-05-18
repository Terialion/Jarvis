"""ChunkRenderer — single source of truth for ModelChunk processing.

Used by PersistentTUI (TUI mode) and one-shot streaming to eliminate
duplicated chunk-handling logic. Both paths share the same state tracking
and rendering decisions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..agent.types import ModelChunk
from .streaming import (
    _TOOL_DISPLAY,
    _format_elapsed,
    _format_tool_args,
    _format_token_count,
)
from .tui_utils import strip_artifacts, format_tool_result


@dataclass
class ChunkRendererState:
    """Mutable state for a single streaming turn."""
    answer_chunks: list[str] = field(default_factory=list)
    thinking_blocks: list[str] = field(default_factory=list)
    tools_collected: list[dict] = field(default_factory=list)
    seen_tool_ids: set[str] = field(default_factory=set)
    processed_text: bool = False
    started_at: float = 0.0
    token_count: int = 0
    current_tool_started_at: float | None = None
    _done: bool = False


class ChunkRenderer:
    """Process ModelChunk objects and track streaming turn state.

    Used by both:
    - PersistentTUI._poll_bridge_sync() (TUI mode)
    - _run_bridge_blocking() in cli.py (initial prompt)
    - _run_agent_streaming() in cli.py (one-shot mode, via adapter)

    Output is driven by an optional ``write_line`` callback.
    """

    def __init__(
        self,
        state: ChunkRendererState | None = None,
        *,
        write_line: Callable[[str], None] | None = None,
    ) -> None:
        self.state = state or ChunkRendererState()
        self._write_line = write_line or (lambda _: None)

    # ── Public API ──────────────────────────────────────────────────────────

    def handle_chunk(self, chunk: ModelChunk) -> None:
        """Dispatch a single chunk to the appropriate handler."""
        kind = chunk.kind if hasattr(chunk, "kind") else chunk.get("kind", "")
        if kind == "text_delta":
            self._handle_text_delta(chunk)
        elif kind == "reasoning_delta":
            self._handle_reasoning_delta(chunk)
        elif kind == "progress_delta":
            self._handle_progress_delta(chunk)
        elif kind == "tool_call_delta":
            self._handle_tool_call_delta(chunk)
        elif kind == "done":
            self._handle_done(chunk)

    def finalize(self) -> tuple[str, str, list[dict]]:
        """Return (answer_text, thinking_text, tools_data) for post-turn rendering."""
        s = self.state
        full_answer = "".join(s.answer_chunks)
        full_answer = strip_artifacts(full_answer)

        full_thinking = "".join(s.thinking_blocks)
        full_thinking = strip_artifacts(full_thinking)

        # If model put everything in reasoning, use thinking as answer
        if not full_answer.strip() and full_thinking.strip():
            full_answer = full_thinking

        return full_answer, full_thinking, list(s.tools_collected)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.state.started_at

    @property
    def has_thinking(self) -> bool:
        return bool(self.state.thinking_blocks)

    @property
    def has_tools(self) -> bool:
        return bool(self.state.tools_collected)

    # ── Handlers ────────────────────────────────────────────────────────────

    def _handle_text_delta(self, chunk: ModelChunk) -> None:
        text = (chunk.text_delta or "") if hasattr(chunk, "text_delta") else chunk.get("text_delta", "")
        if not text.strip():
            return
        self.state.processed_text = True
        clean = strip_artifacts(text.strip())
        if not clean:
            return
        if clean.startswith("[Tool "):
            elapsed_str = ""
            if self.state.current_tool_started_at:
                elapsed_str = f" \x1b[2m[{_format_elapsed(time.monotonic() - self.state.current_tool_started_at)}]\x1b[0m"
                self.state.current_tool_started_at = None
            self._write_line(format_tool_result(clean, elapsed_str))
        else:
            self.state.answer_chunks.append(clean)

    def _handle_reasoning_delta(self, chunk: ModelChunk) -> None:
        text = (chunk.reasoning_delta or "") if hasattr(chunk, "reasoning_delta") else chunk.get("reasoning_delta", "")
        if text.strip():
            self.state.thinking_blocks.append(text)

    def _handle_progress_delta(self, chunk: ModelChunk) -> None:
        text = (chunk.progress_delta or "") if hasattr(chunk, "progress_delta") else chunk.get("progress_delta", "")
        if text.strip():
            self.state.thinking_blocks.append(text)

    def _handle_tool_call_delta(self, chunk: ModelChunk) -> None:
        call_id = (chunk.tool_call_id or "") if hasattr(chunk, "tool_call_id") else chunk.get("tool_call_id", "")
        if call_id and call_id in self.state.seen_tool_ids:
            return
        name = (chunk.tool_name or "") if hasattr(chunk, "tool_name") else chunk.get("tool_name", "")
        if not name:
            return
        if call_id:
            self.state.seen_tool_ids.add(call_id)
        self.state.current_tool_started_at = time.monotonic()

        display = _TOOL_DISPLAY.get(name, name.rsplit(".", 1)[-1] if "." in name else name)
        args = (chunk.tool_arguments_delta or "") if hasattr(chunk, "tool_arguments_delta") else chunk.get("tool_arguments_delta", "")
        args_str = _format_tool_args(name, args)
        if args_str:
            self._write_line(f"  ● {display} {args_str}")
        else:
            self._write_line(f"  ● {display}")

        self.state.tools_collected.append({
            "name": name,
            "display": display,
            "args": args_str,
            "status": "ok",
        })

    def _handle_done(self, chunk: ModelChunk) -> None:
        self.state._done = True
        if not self.state.processed_text:
            reason = (chunk.finish_reason or "") if hasattr(chunk, "finish_reason") else chunk.get("finish_reason", "")
            if reason and reason not in ("stop", ""):
                self._write_line(f"[Agent stopped: {reason}]")
