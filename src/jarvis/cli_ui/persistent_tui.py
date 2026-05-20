"""Persistent TUI — fixed bottom input bar with terminal-native scrollback.

Mimics Claude Code / Codex CLI: the input bar stays visible at all times,
output streams to stdout (terminal scrollback) above it.

Uses prompt_toolkit Application + Layout (not PromptSession shortcut).
No alternate screen — native terminal scrollback just works.
"""

from __future__ import annotations

import asyncio
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.widgets import TextArea
from rich.text import Text as RichText

from .streaming import _format_elapsed
from .tui_utils import (
    _PROMPT_FORMATTED,
    TUI_STYLE,
    SlashCompleter,
    build_status_indicators,
    render_markdown,
    rich_to_ansi,
)

# Styles and prompt formatting are imported from tui_utils


# SlashCompleter imported from tui_utils


# render_markdown imported from tui_utils


# ── PersistentTUI ------------------------------------------------------------

class PersistentTUI:
    """REPL with persistent bottom input bar matching Claude Code / Codex CLI.

    The input bar stays visible at all times. Output is written to stdout
    through prompt_toolkit's print_formatted_text, appearing above the bar
    in the terminal scrollback.

    Usage::

        tui = PersistentTUI(project_root=".", model_name="deepseek-v4")
        tui.register_slash_commands([("/help", "Show help", "misc", "implemented")])
        tui.set_handlers(slash_handler=..., natural_handler=...)
        tui.write_line(header)
        tui.run()
    """

    def __init__(
        self,
        *,
        project_root: str = ".",
        model_name: str = "unknown",
        session_name: str = "cli_shell",
    ) -> None:
        self.project_root = project_root
        self.model_name = model_name
        self.session_name = session_name
        self._permission_mode = "default"  # default, plan, accept_edits, bypass

        self._slash_completer = SlashCompleter()
        history_path = Path(".jarvis") / "cli_history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self._input_history = FileHistory(str(history_path))

        # Cross-thread ask_user state
        self._ask_user_requested = threading.Event()
        self._ask_user_answered = threading.Event()
        self._ask_user_config: dict | None = None
        self._ask_user_answer: dict | None = None

        # Thinking collapse/expand state
        self._last_thinking_text: str = ""
        self._thinking_expanded: bool = False

        # Tools collapse/expand state (Ctrl+O toggle)
        self._last_tools_data: list[dict] = []
        self._tools_expanded: bool = False

        # Toggle block line count tracking
        self._last_toggle_lines: int = 0

        # Status line
        self._last_status_line: str = ""
        self._last_latency: str = ""
        self._last_tokens: str = ""

        # Bridge reference (set during agent execution)
        self._bridge: Any = None
        self._cancel_requested = threading.Event()

        # Handlers
        self._slash_handler: Any = None
        self._natural_handler: Any = None

        # Built lazily
        self._app: Application | None = None
        self._input_area: TextArea | None = None

        # Tracking for bridge polling
        self._current_bridge_task: asyncio.Task | None = None

        # Flag: set by write_line/write when output was written directly to
        # stdout while the app is running. _sync_renderer() uses this to
        # force a full repaint of the input bar at the new cursor position.
        self._output_was_written: bool = False

    # ── Public API ───────────────────────────────────────────────────────

    def register_slash_commands(self, commands: list[tuple[str, str, str, str]]) -> None:
        """Register commands for autocomplete."""
        self._slash_completer.register_commands(commands)

    def load_builtin_commands(self) -> None:
        """Populate slash completer from the command spec registry (including plugins)."""
        try:
            from ..cli_command_map import list_command_specs
            commands: list[tuple[str, str, str, str]] = []
            for spec in list_command_specs():
                if spec.name.startswith("/") and spec.status == "implemented":
                    commands.append((spec.name, spec.description, spec.category, spec.status))
            self._slash_completer.register_commands(commands)
        except Exception:
            pass

    def set_handlers(
        self,
        slash_handler: Any,
        natural_handler: Any,
    ) -> None:
        """Set handlers for slash commands and natural language input."""
        self._slash_handler = slash_handler
        self._natural_handler = natural_handler

    def write_line(self, text: str = "") -> None:
        """Write a line to stdout above the application layout."""
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        self._output_was_written = True

    def write(self, text: str) -> None:
        """Write text to stdout without trailing newline."""
        sys.stdout.write(text)
        sys.stdout.flush()
        self._output_was_written = True

    def _sync_renderer(self) -> None:
        """Force prompt_toolkit to fully re-render the input bar.

        Call after writing output directly to stdout while the app is running.
        Resets renderer state so the next render is a full repaint (not diff),
        correctly positioning the input bar at the new cursor position.
        """
        if not self._output_was_written or not self._app:
            return
        self._output_was_written = False
        try:
            self._app.renderer._last_screen = None
            self._app.renderer._cursor_pos = type(self._app.renderer._cursor_pos)(0, 0)
        except Exception:
            pass
        self._app.invalidate()

    def _scroll_to_bottom(self) -> None:
        """Push the cursor to the bottom of the terminal.

        Writes enough newlines to move the cursor from its current position
        to near the bottom of the terminal window, so the input bar renders
        at the bottom edge like in Claude Code.
        """
        import shutil
        try:
            term_rows = shutil.get_terminal_size().lines
            # Write enough newlines to push cursor near the bottom.
            # Leave 2 lines for the input area and a small margin.
            lines_needed = max(0, term_rows - 3)
            if lines_needed > 0:
                sys.stdout.write("\n" * lines_needed)
                sys.stdout.flush()
        except Exception:
            # If we can't detect terminal size, write a reasonable default
            sys.stdout.write("\n" * 16)
            sys.stdout.flush()

    def _pft(self, text: Any) -> None:
        """Write via prompt_toolkit's print_formatted_text (handles FormattedText)."""
        from prompt_toolkit import print_formatted_text as pft
        pft(text)

    def exit(self) -> None:
        """Request application exit."""
        if self._app:
            self._app.exit()

    # ── Build ────────────────────────────────────────────────────────────

    def _build_input_area(self) -> TextArea:
        """Create the input TextArea with prompt, completer, history, and auto-suggest."""
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

        area = TextArea(
            prompt=_PROMPT_FORMATTED,
            completer=self._slash_completer,
            history=self._input_history,
            auto_suggest=AutoSuggestFromHistory(),
            accept_handler=self._on_submit,
            multiline=True,
            style="class:input-area",
        )
        return area

    def _build_layout(self) -> Layout:
        """Build the application layout."""
        self._input_area = self._build_input_area()

        root = HSplit([
            Window(height=0),
            self._input_area,
        ])

        return Layout(root)

    def _build_key_bindings(self) -> KeyBindings:
        """Build global key bindings for the application."""
        kb = KeyBindings()

        @kb.add("c-c")
        def _exit(event):
            if self._bridge is not None:
                self._cancel_requested.set()
            else:
                event.app.exit()

        @kb.add("c-t")
        def _toggle_thinking(event):
            if not self._last_thinking_text:
                return
            self._thinking_expanded = not self._thinking_expanded
            self._render_toggle_block()

        @kb.add("c-o")
        def _toggle_tools(event):
            if not self._last_tools_data:
                return
            self._tools_expanded = not self._tools_expanded
            self._render_toggle_block()

        @kb.add("enter")
        def _smart_enter(event):
            """Enter at end of input = submit; Enter mid-input = newline."""
            buffer = event.app.current_buffer
            if buffer.cursor_position == len(buffer.text):
                # Cursor at end — submit
                self._on_submit(buffer)
            else:
                buffer.insert_text("\n")

        @kb.add("escape", "enter")
        def _force_newline(event):
            """Alt+Enter or Esc+Enter always inserts a newline."""
            event.app.current_buffer.insert_text("\n")

        @kb.add("s-tab")
        def _cycle_permission_mode(event):
            """Cycle permission mode: default → plan → accept_edits."""
            modes = ["default", "plan", "accept_edits"]
            current = getattr(self, '_permission_mode', 'default')
            idx = modes.index(current) if current in modes else 0
            next_mode = modes[(idx + 1) % len(modes)]
            self._permission_mode = next_mode
            self._pft(FormattedText([
                ("class:muted", f"  Permission mode: {next_mode}")
            ]))

        @kb.add("c-r")
        def _history_search(event):
            """Ctrl+R: search command history and fill into buffer."""
            buffer = event.app.current_buffer
            try:
                history_strings = list(self._input_history.load_history_strings())
            except Exception:
                return
            if not history_strings:
                return

            # Show a minimal prompt for the search term
            from prompt_toolkit.shortcuts import prompt as pt_prompt
            try:
                search = pt_prompt(
                    "(reverse-i-search)`': ",
                    style=TUI_STYLE,
                )
            except (EOFError, KeyboardInterrupt):
                return

            if search:
                search_lower = search.lower()
                for entry in reversed(history_strings):
                    if search_lower in entry.lower():
                        buffer.text = entry
                        buffer.cursor_position = len(entry)
                        break

        return kb

    # ── Accept handler ───────────────────────────────────────────────────

    def _on_submit(self, buffer: Buffer) -> bool:
        """Handle user input submission (Enter pressed)."""
        raw = buffer.text
        buffer.reset()

        if not raw or not raw.strip():
            return True

        raw = raw.strip()

        # Guard: don't accept natural language while bridge is running
        if not raw.startswith("/") and self._bridge is not None:
            self._pft(FormattedText([("class:warning", "  Agent is still running. Press Ctrl+C to cancel.")]))
            return True

        # Echo user input to scrollback
        self._pft(FormattedText([("class:user", "> "), ("", raw)]))

        # Dispatch
        if raw.startswith("/"):
            if self._slash_handler:
                result = self._slash_handler(raw)
                if result is None:
                    self._app.exit()
                    return True
                if result.strip():
                    self.write_line(result)
        else:
            if self._natural_handler:
                self._natural_handler(raw)

        return True

    # ── Run ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the application event loop. Blocks until exit."""
        if self._app is None:
            # Push cursor to terminal bottom before starting the app,
            # so the input bar renders at the bottom edge.
            self._scroll_to_bottom()

            self._app = Application(
                layout=self._build_layout(),
                key_bindings=self._build_key_bindings(),
                style=TUI_STYLE,
                full_screen=False,
                mouse_support=False,
            )

        try:
            self._app.run()
        except KeyboardInterrupt:
            pass

    # ── Agent bridge ─────────────────────────────────────────────────────

    def run_bridge(self, prompt_text: str) -> None:
        """Start agent bridge in background thread, schedule synchronous polling.

        Uses loop.call_later for self-scheduling instead of create_task(),
        which fixes the Windows hang where the async task was starved by
        prompt_toolkit's event loop.
        """
        from .agent_bridge import AgentThreadBridge

        bridge = AgentThreadBridge(
            permission_mode="workspace_write",
            auto_approve=True,
        )
        self._bridge = bridge
        self._cancel_requested.clear()
        bridge.start(prompt=prompt_text, tui=self, session_id=self.session_name)

        # Clear old toggle block and add separator
        self._clear_toggle_block()
        self.write_line()

        # Initialize polling state
        from .chunk_renderer import ChunkRenderer, ChunkRendererState
        renderer_state = ChunkRendererState(started_at=time.monotonic())
        renderer = ChunkRenderer(renderer_state, write_line=self.write_line)
        self._poll_state = {
            "bridge": bridge,
            "chunk_queue": bridge.chunk_queue,
            "renderer": renderer,
            "poll_count": 0,
            "_last_status_len": 0,
        }

        # Schedule first poll on the event loop
        loop = asyncio.get_event_loop()
        loop.call_soon(self._poll_bridge_sync)

    def _poll_bridge_sync(self) -> None:
        """Sync callback: poll bridge chunk queue, write output to stdout.

        Self-schedules via loop.call_later(0.05) until the sentinel None
        chunk arrives or the user cancels. Uses ChunkRenderer to process
        chunks — same class used by one-shot mode.
        """
        from jarvis.core.debug_log import debug_log, is_debug_enabled
        _dbg = is_debug_enabled()

        state = self._poll_state
        renderer = state["renderer"]

        # Process all available chunks (non-blocking drain)
        while True:
            state["poll_count"] += 1

            if self._cancel_requested.is_set():
                if _dbg:
                    debug_log("tui", f"Ctrl+C cancel at poll #{state['poll_count']}")
                self._finalize_turn(state)
                return

            try:
                chunk = state["chunk_queue"].get(timeout=0.01)
            except queue.Empty:
                # No chunk available — check ask_user, show status, reschedule
                if self._ask_user_requested.is_set():
                    self._check_ask_user()
                self._render_spinner_status(state)
                loop = asyncio.get_event_loop()
                loop.call_later(0.05, self._poll_bridge_sync)
                return

            # Clear spinner status line before writing chunk output
            _last = state["_last_status_len"]
            if _last:
                sys.stdout.write("\r" + " " * _last + "\r")
                state["_last_status_len"] = 0

            if chunk is None:  # Sentinel: agent done
                if _dbg:
                    debug_log("tui", f"sentinel at poll #{state['poll_count']}")
                self._finalize_turn(state)
                return

            try:
                renderer.handle_chunk(chunk)
            except Exception:
                if _dbg:
                    debug_log("tui", "handle_chunk failed, skipping chunk")
                continue

    def _render_spinner_status(self, state: dict) -> None:
        """Show spinner status line on the current terminal line."""
        renderer = state["renderer"]
        elapsed = renderer.elapsed
        if renderer.has_tools:
            text = f"\x1b[2m  ● Running tools ({_format_elapsed(elapsed)})...\x1b[0m"
        elif renderer.has_thinking:
            text = f"\x1b[2m  ● Thinking ({_format_elapsed(elapsed)})...\x1b[0m"
        else:
            text = f"\x1b[2m  ● Thinking ({_format_elapsed(elapsed)})...\x1b[0m"
        prev_len = state["_last_status_len"]
        if len(text) < prev_len:
            text = text + " " * (prev_len - len(text))
        sys.stdout.write("\r" + text)
        sys.stdout.flush()
        state["_last_status_len"] = len(text)

    def _finalize_turn(self, state: dict) -> None:
        """Render final answer, status line, and toggle block after agent completes."""
        # Clear spinner status line
        _last = state["_last_status_len"]
        if _last:
            sys.stdout.write("\r" + " " * _last + "\r")
            sys.stdout.flush()

        renderer = state["renderer"]
        answer, thinking, tools = renderer.finalize()

        # Store thinking text for Ctrl+T toggle
        if thinking.strip():
            self._last_thinking_text = thinking.strip()
            self._thinking_expanded = False
        else:
            self._last_thinking_text = ""
            self._thinking_expanded = False

        self._last_tools_data = tools
        self._tools_expanded = False

        # Show file changes if tools modified files
        self._render_file_changes(tools)

        # Render final answer as markdown
        if answer.strip():
            width = min(self._terminal_width(), 100)
            rendered = render_markdown(answer.strip(), width=max(width, 40))
            self.write(rendered + "\n")

        # Cache status line with model, branch, latency, cost, perm mode
        elapsed = renderer.elapsed
        self._last_latency = _format_elapsed(elapsed)
        self._last_tokens = ""

        status_parts = [f"[dim]  {self.model_name}"]
        branch = self._get_git_branch()
        if branch:
            status_parts.append(f" · {branch}")
        status_parts.append(f" · {self._last_latency}")
        if self._permission_mode != "default":
            status_parts.append(f" · [bold]{self._permission_mode}[/bold]")
        indicators = build_status_indicators(self.project_root)
        if indicators:
            status_parts.append(indicators)
        status = "".join(status_parts) + "[/dim]"
        self._last_status_line = status

        # Send desktop notification for long-running turns (>15s)
        if elapsed > 15:
            summary = (answer[:120] + "...") if len(answer) > 120 else answer
            if summary.strip():
                self._send_notification("Jarvis", summary.strip())

        # Render toggle block below answer
        self._render_toggle_block()

        # Force prompt_toolkit to redraw the input bar at the bottom after
        # all turn output was written directly to stdout.
        self._sync_renderer()

        self._bridge = None
        self._poll_state = None

    # ── Status helpers ──────────────────────────────────────────────────

    def _get_git_branch(self) -> str:
        """Return current git branch name, or empty string."""
        try:
            head = Path(self.project_root) / ".git" / "HEAD"
            if head.exists():
                ref = head.read_text().strip()
                if ref.startswith("ref: refs/heads/"):
                    return ref[len("ref: refs/heads/"):]
        except Exception:
            pass
        return ""

    def _render_file_changes(self, tools: list[dict]) -> None:
        """Show modified files after turn completion (Claude Code style)."""
        write_tools = {"file_editor.write_file", "file_editor.replace_text",
                       "file_editor.insert_text", "patch.apply"}
        changed = []
        for t in tools:
            if t.get("name") in write_tools:
                args = t.get("args", "")
                path = args.split(" · ")[0] if " · " in args else args
                if path and path not in changed:
                    changed.append(path)
        if changed:
            lines = ["[dim]  Files modified:[/dim]"]
            for f in changed[:10]:
                lines.append(f"[dim]    {f}[/dim]")
            self.write_line("\n".join(lines))

    @staticmethod
    def _send_notification(title: str, body: str) -> None:
        """Send a desktop notification. Non-blocking, best-effort."""
        import platform
        import subprocess
        import threading

        def _notify() -> None:
            try:
                system = platform.system()
                if system == "Windows":
                    try:
                        from win10toast import ToastNotifier
                        ToastNotifier().show_toast(title, body, duration=5, threaded=True)
                    except ImportError:
                        pass
                elif system == "Darwin":
                    subprocess.run(
                        ["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                        capture_output=True, timeout=3,
                    )
                elif system == "Linux":
                    subprocess.run(
                        ["notify-send", title, body, "-t", "5000"],
                        capture_output=True, timeout=3,
                    )
            except Exception:
                pass

        threading.Thread(target=_notify, daemon=True).start()

    def _clear_toggle_block(self) -> None:
        """Clear the old toggle block from the previous turn."""
        if self._last_toggle_lines > 0:
            n = self._last_toggle_lines
            sys.stdout.write(f"\x1b[{n + 1}A")
            for _ in range(n):
                sys.stdout.write("\x1b[K\n")
            sys.stdout.write("\n")
            self._last_toggle_lines = 0
            sys.stdout.flush()

    # ── Toggle block rendering ───────────────────────────────────────────

    def _render_toggle_block(self) -> None:
        """Render thinking + tools toggle hints in-place above the input bar."""
        old_lines = self._last_toggle_lines

        if old_lines > 0:
            sys.stdout.write(f"\x1b[{old_lines}A")

        self._last_toggle_lines = 0

        # No toggle data — clear old lines, optionally re-render status
        if not self._last_thinking_text and not self._last_tools_data:
            for _ in range(old_lines):
                sys.stdout.write("\x1b[K\n")
            if old_lines > 0:
                sys.stdout.write(f"\x1b[{old_lines}A")
            if self._last_status_line:
                ansi = rich_to_ansi(
                    RichText.from_markup(self._last_status_line),
                    width=self._terminal_width()
                )
                sys.stdout.write(ansi + "\n")
                self._last_toggle_lines = ansi.count("\n") + 1
            sys.stdout.flush()
            return

        # Build new toggle content
        from .streaming import StreamingDisplay

        parts: list[str] = []
        if self._last_thinking_text:
            parts.append(
                StreamingDisplay.render_thinking(
                    self._last_thinking_text, expanded=self._thinking_expanded
                )
            )
        if self._last_tools_data:
            parts.append(
                StreamingDisplay.render_tools_summary(
                    self._last_tools_data, expanded=self._tools_expanded
                )
            )

        if self._last_status_line:
            parts.append("\n" + self._last_status_line)

        combined = "".join(parts)
        ansi = rich_to_ansi(
            RichText.from_markup(combined),
            width=self._terminal_width()
        )

        # Write new toggle content, plus trailing newline so cursor lands
        # on a fresh line — prompt_toolkit places the input bar below
        sys.stdout.write(ansi + "\n")

        # Clear any leftover lines from previous (longer) toggle block
        new_lines = ansi.count("\n") + 1
        if new_lines < old_lines:
            for _ in range(old_lines - new_lines):
                sys.stdout.write("\x1b[K\n")
            sys.stdout.write(f"\x1b[{old_lines - new_lines}A")

        self._last_toggle_lines = new_lines
        sys.stdout.flush()

        # Invalidate the app so prompt_toolkit re-renders the input bar
        if self._app:
            self._app.invalidate()

    # ── ask_user cross-thread protocol ────────────────────────────────────

    def request_user_input(
        self,
        question: str,
        *,
        header: str = "",
        options: list[dict[str, str]] | None = None,
        multi_select: bool = False,
    ) -> dict:
        """Called from bridge thread to request user input. Blocks bridge thread."""
        self._ask_user_config = {
            "question": question,
            "header": header,
            "options": options or [],
            "multi_select": multi_select,
        }
        self._ask_user_answer = None
        self._ask_user_requested.set()

        self._ask_user_answered.wait()
        self._ask_user_answered.clear()

        return self._ask_user_answer or {"answers": {}, "note": "no_answer"}

    def _check_ask_user(self) -> bool:
        """Check if bridge thread is waiting for user input. Called from sync poll loop.

        Shows the permission prompt and reads user input via a thread pool
        to avoid blocking the prompt_toolkit event loop.
        """
        if not self._ask_user_requested.is_set():
            return False

        config = self._ask_user_config
        if config is None:
            self._ask_user_answer = {"answers": {}, "note": "no_config"}
        else:
            self._ask_user_answer = self._prompt_user_sync(
                config["question"],
                config["header"],
                config["options"],
                config["multi_select"],
            )

        self._ask_user_requested.clear()
        self._ask_user_answered.set()
        return True

    async def _check_ask_user_async(self, loop) -> bool:
        """Check if bridge thread is waiting for user input. Called from async poll task."""
        if not self._ask_user_requested.is_set():
            return False

        config = self._ask_user_config
        if config is None:
            self._ask_user_answer = {"answers": {}, "note": "no_config"}
        else:
            # Run blocking prompt in executor to not block the event loop
            answer = await loop.run_in_executor(
                None, self._prompt_user_sync, config["question"],
                config["header"], config["options"], config["multi_select"],
            )
            self._ask_user_answer = answer

        self._ask_user_requested.clear()
        self._ask_user_answered.set()
        return True

    def _prompt_user_sync(
        self,
        question: str,
        header: str = "",
        options: list[dict[str, str]] | None = None,
        multi_select: bool = False,
    ) -> dict:
        """Show a permission prompt and wait for user response.

        Called via loop.run_in_executor — runs in a thread pool thread,
        so we can safely use blocking sys.stdin.readline().
        """
        from rich.panel import Panel

        opts = options or []

        body = RichText()
        if header:
            body.append(f"{header}\n", style="bold warning")
        body.append(f"{question}\n\n", style="")
        for i, opt in enumerate(opts, 1):
            label = opt.get("label", f"Option {i}")
            desc = opt.get("description", "")
            body.append(f"  [{i}] ", style="bold")
            body.append(f"{label}", style="bold success")
            if desc:
                body.append(f"  —  {desc}", style="dim")
            body.append("\n")
        if multi_select:
            body.append("\nEnter numbers (e.g. 1,3) or 'all': ", style="dim")
        else:
            body.append(f"\nEnter number (1-{len(opts)}) or type label: ", style="dim")

        width = self._terminal_width()
        panel = Panel(body, title="Permission Required", title_align="left",
                       border_style="warning", padding=(1, 2))
        self.write_line(rich_to_ansi(panel, width=max(width, 40)))

        # Read from stdin directly — we're in a thread, blocking is fine
        try:
            raw = sys.stdin.readline().strip()
        except (EOFError, KeyboardInterrupt):
            return {"answers": {}, "note": "user_cancelled"}

        if not raw:
            return {"answers": {}, "note": "no_selection"}
        if multi_select:
            indices: list[int] = []
            if raw.lower() == "all":
                indices = list(range(1, len(opts) + 1))
            else:
                for x in raw.split(","):
                    x = x.strip()
                    if x.isdigit():
                        indices.append(int(x))
            selected = {}
            for i in indices:
                if 1 <= i <= len(opts):
                    label = opts[i - 1].get("label", "")
                    selected[label] = label
            return {"answers": selected}

        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(opts):
                label = opts[i - 1].get("label", "")
                return {"answers": {label: label}}

        for opt in opts:
            if opt.get("label", "").lower() == raw.lower():
                return {"answers": {opt["label"]: opt["label"]}}

        return {"answers": {raw: raw}}

    # ── Helpers ──────────────────────────────────────────────────────────

    def _terminal_width(self) -> int:
        try:
            if self._app and self._app.output:
                return self._app.output.get_size().columns - 4
        except Exception:
            pass
        return 76

    # _strip_artifacts, _format_tool_result, _build_status_indicators
    # are imported from tui_utils as standalone functions.
