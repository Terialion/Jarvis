"""AgentThreadBridge — runs AgentLoop in a worker thread, streams chunks to TUI.

Worker thread: AgentLoop.run_turn_stream() → chunk_queue.put(chunk)
Main thread:  chunk_queue.get() → PersistentTUI._poll_bridge() → writes to stdout
Cross-thread AskUser: threading.Event (worker blocks, main thread resolves)
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from ..agent.types import ModelChunk


class AgentThreadBridge:
    """Runs AgentLoop in a background thread, streaming chunks to the TUI.

    Usage::

        bridge = AgentThreadBridge(
            permission_mode="workspace_write",
            auto_approve=True,
        )
        bridge.start(prompt="hi", tui=my_tui, session_id=None)

        # Poll from main thread:
        while True:
            chunk = bridge.chunk_queue.get(timeout=0.05)
            if chunk is None:  # sentinel = agent done
                break
            # process chunk...
    """

    def __init__(
        self,
        *,
        permission_mode: str = "workspace_write",
        auto_approve: bool = True,
        max_steps: int = 20,
        timeout_s: int = 300,
    ) -> None:
        self.permission_mode = permission_mode
        self.auto_approve = auto_approve
        self.max_steps = max_steps
        self.timeout_s = timeout_s

        self.chunk_queue: queue.Queue[ModelChunk | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(
        self,
        prompt: str,
        *,
        tui: Any = None,
        session_id: str | None = None,
    ) -> None:
        """Start agent execution in a background thread."""
        if self._running:
            raise RuntimeError("AgentThreadBridge is already running")

        # Pre-warm the skill registry cache on the calling (main) thread.
        # On Windows, file I/O in daemon threads is 30-50x slower than on
        # the main thread. Running the scan here avoids a 200s stall in the
        # worker thread.
        self._warm_skill_cache()

        self._running = True
        self._thread = threading.Thread(
            target=self._run_agent,
            args=(prompt, tui, session_id),
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _warm_skill_cache() -> None:
        """Trigger skill registry scan on the current thread to populate the
        cross-instance cache. In worker threads this scan is 30-50x slower
        on Windows, causing turn timeouts."""
        try:
            from ..skills.registry import SkillRegistry
            reg = SkillRegistry()
            _ = reg.export_index()
        except Exception:
            pass

    # ── Worker thread ──────────────────────────────────────────────────

    def _run_agent(
        self,
        prompt: str,
        tui: Any,
        session_id: str | None,
    ) -> None:
        """Run AgentLoop in this worker thread, streaming chunks to the queue."""
        from ..agent.loop import AgentLoop
        from ..agent.types import ChatInput
        from ..core.debug_log import debug_log, is_debug_enabled

        cwd = str(Path.cwd())
        _dbg = is_debug_enabled()

        def _tui_user_prompt(*, question: str, header: str, options: list, multi_select: bool) -> dict:
            return self._bridge_ask_user(tui, question, header, options, multi_select)

        try:
            if _dbg:
                debug_log("bridge", f"thread start: prompt={prompt[:120]!r} session_id={session_id!r}")
            loop = AgentLoop(
                project_root=cwd,
                permission_mode=self.permission_mode,
                auto_approve=self.auto_approve,
                max_steps=self.max_steps,
                timeout_s=self.timeout_s,
                user_prompt=_tui_user_prompt,
            )
            if _dbg:
                debug_log("bridge", f"AgentLoop created: model={loop._model_name} max_steps={loop.max_steps}")

            chat_input = ChatInput(
                text=prompt,
                cwd=cwd,
                session_id=session_id,
                metadata={"source": "jarvis.cli.tui", "mode": "tui_bridge"},
            )

            chunk_count = 0
            for chunk in loop.run_turn_stream(chat_input):
                chunk_count += 1
                if _dbg:
                    kind = getattr(chunk, "kind", "?")
                    extra = ""
                    if kind == "tool_call_delta":
                        extra = f" name={getattr(chunk, 'tool_name', '?')}"
                    elif kind == "done":
                        extra = f" reason={getattr(chunk, 'finish_reason', '?')}"
                    debug_log("bridge", f"chunk #{chunk_count}: {kind}{extra}")
                try:
                    self.chunk_queue.put(chunk)
                except Exception:
                    pass  # Queue closed, TUI exited
            if _dbg:
                debug_log("bridge", f"run_turn_stream done: {chunk_count} chunks")

        except Exception as exc:
            if _dbg:
                debug_log("bridge", f"EXCEPTION: {exc!r}")
            try:
                self.chunk_queue.put(ModelChunk(
                    kind="text_delta",
                    text_delta=f"\n[Agent error: {exc}]",
                ))
                self.chunk_queue.put(ModelChunk(kind="done", finish_reason="error"))
            except Exception:
                pass

        finally:
            if _dbg:
                debug_log("bridge", "sending None sentinel")
            try:
                self.chunk_queue.put(None)  # Sentinel: agent complete
            except Exception:
                pass
            self._running = False

    # ── Cross-thread AskUser bridging ──────────────────────────────────

    def _bridge_ask_user(
        self,
        tui: Any,
        question: str,
        header: str,
        options: list,
        multi_select: bool,
    ) -> dict:
        """Call tui.request_user_input() from the worker thread.

        Uses threading.Event to block the worker thread until the main
        thread resolves the user prompt.
        """
        if tui is None:
            return {"answers": {}, "note": "no_tui_available"}

        try:
            return tui.request_user_input(
                question=question,
                header=header,
                options=options,
                multi_select=multi_select,
            )
        except Exception as e:
            return {"answers": {}, "note": f"bridge_error: {e}"}
