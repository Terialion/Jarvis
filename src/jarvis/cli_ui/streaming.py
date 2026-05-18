"""Streaming display using rich.Live for real-time agent output."""

from __future__ import annotations

import json
import random
import time

from rich.console import Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel as RichPanel
from rich.text import Text

from .console import get_console
from .render import _normalize_markdown

# Spinner animation frames — matches Claude Code's "evaporating" dot sequence
SPINNER_FRAMES = ["·", "✢", "✳", "✶", "✻", "✽"]

SPINNER_VERBS = [
    "Analyzing", "Brewing", "Calculating", "Cogitating", "Combobulating",
    "Compiling", "Computing", "Contemplating", "Deciding", "Decoding",
    "Deliberating", "Distilling", "Evaluating", "Evaporating", "Fermenting",
    "Gleaning", "Ideating", "Inspecting", "Loading", "Marinating",
    "Mulling", "Parsing", "Percolating", "Pondering", "Processing",
    "Reading", "Reasoning", "Reflecting", "Resolving", "Ruminating",
    "Scanning", "Searching", "Simulating", "Synthesizing", "Thinking",
    "Weighing",
]

# Maps internal tool names → Claude Code-style display names
_TOOL_DISPLAY: dict[str, str] = {
    "repo_reader.read_file": "Read",
    "workspace.read_file": "Read",
    "repo_reader.search_files": "Grep",
    "repo_reader.glob": "Glob",
    "repo_reader.search_symbol": "Grep",
    "repo_reader.list_tree": "List",
    "file_editor.write_file": "Write",
    "file_editor.replace_text": "Edit",
    "file_editor.insert_text": "Edit",
    "file_editor.diff": "Diff",
    "patch.apply": "Write",
    "command_runner.run": "Bash",
    "shell.run": "Bash",
    "test_runner.run_test": "Test",
    "web.search": "WebSearch",
    "web.fetch": "WebFetch",
    "web.browse": "WebBrowse",
    "skill.load": "Skill",
    "skill.run": "Skill",
    "skill.list": "Skill",
    "skill.invoke": "Skill",
    "task.create": "TaskCreate",
    "task.update": "TaskUpdate",
    "task.list": "TaskList",
    "task.delegate": "Agent",
    "checkpoint.create": "Checkpoint",
    "checkpoint.rollback": "Checkpoint",
    "checkpoint.list": "Checkpoint",
    "memory.search": "MemorySearch",
    "memory.write": "MemoryWrite",
    "memory.remember": "MemoryRemember",
    "bg.task.run": "BgTask",
    "bg.task.check": "BgTask",
    "bg.task.cancel": "BgTask",
    "mcp.list_servers": "MCP",
    "mcp.call": "MCP",
    "agent.ask_user": "AskUser",
}


def _format_tool_args(name: str, raw_args: str) -> str:
    """Parse JSON tool args into a compact human-readable string.

    Returns empty string if args can't be parsed or are empty.
    """
    if not raw_args or not raw_args.strip():
        return ""
    try:
        args: dict = json.loads(raw_args)
    except (json.JSONDecodeError, TypeError):
        # Partial JSON during streaming — show raw truncated
        return raw_args[:60]
    if not isinstance(args, dict) or not args:
        return ""

    # File reading tools — show path + optional line range
    if name in ("repo_reader.read_file", "workspace.read_file"):
        path = str(args.get("path") or args.get("file_path") or "")
        sl = args.get("start_line")
        el = args.get("end_line")
        if sl is not None and el is not None:
            return f"{path} · lines {sl}-{el}"
        if sl is not None:
            return f"{path} · from line {sl}"
        return path

    # Glob — show pattern
    if name == "repo_reader.glob":
        return str(args.get("pattern", ""))

    # Search/grep — show pattern
    if name in ("repo_reader.search_files", "repo_reader.search_symbol"):
        p = str(args.get("pattern") or args.get("symbol") or "")
        return p

    # File writing — show path + content size
    if name in ("file_editor.write_file", "patch.apply"):
        path = str(args.get("path") or args.get("file_path") or "")
        content = str(args.get("content") or "")
        if content:
            return f"{path} · {len(content)} bytes"
        return path

    # File editing — show path
    if name in ("file_editor.replace_text", "file_editor.insert_text", "file_editor.diff"):
        return str(args.get("path", ""))

    # Shell — show command
    if name in ("command_runner.run", "shell.run"):
        cmd = str(args.get("command", ""))
        return cmd[:100]

    # Test runner — show command
    if name == "test_runner.run_test":
        cmd = str(args.get("command") or "pytest")
        return cmd[:100]

    # Web search — show query
    if name == "web.search":
        return str(args.get("query", ""))

    # Web fetch / browse — show url
    if name in ("web.fetch", "web.browse"):
        return str(args.get("url", ""))

    # Skill — show name
    if name in ("skill.load", "skill.run", "skill.invoke"):
        return str(args.get("name") or args.get("skill_name") or "")

    # Task create — show goal
    if name == "task.create":
        goal = str(args.get("goal", ""))
        steps = len(args.get("steps") or [])
        if steps:
            return f"{goal[:80]} · {steps} steps"
        return goal[:80]

    # Task delegate (Agent) — show task + budget
    if name == "task.delegate":
        task = str(args.get("task", ""))
        budget = args.get("budget_steps")
        if budget:
            return f"{task[:80]} · budget {budget}"
        return task[:80]

    # Task update — show plan_id
    if name == "task.update":
        return str(args.get("plan_id", ""))

    # Checkpoints — show task_id + label
    if name == "checkpoint.create":
        tid = str(args.get("task_id", ""))
        label = str(args.get("label", ""))
        return f"{tid} · {label}" if label else tid
    if name == "checkpoint.rollback":
        tid = str(args.get("task_id", ""))
        cid = str(args.get("checkpoint_id", ""))
        return f"{tid} · {cid}" if cid else tid
    if name == "checkpoint.list":
        return str(args.get("task_id", ""))

    # Memory — show key + query
    if name == "memory.search":
        return str(args.get("query", ""))
    if name in ("memory.write", "memory.remember"):
        return str(args.get("key", ""))

    # Background tasks — show tool_name
    if name == "bg.task.run":
        return str(args.get("tool_name", ""))
    if name in ("bg.task.check", "bg.task.cancel"):
        return str(args.get("task_id", ""))

    # MCP — show server + tool
    if name == "mcp.call":
        server = str(args.get("server", ""))
        tool = str(args.get("tool", ""))
        return f"{server}.{tool}" if tool else server

    # agent.ask_user — show question
    if name == "agent.ask_user":
        return str(args.get("question", ""))[:80]

    # List tree — show path + depth
    if name == "repo_reader.list_tree":
        path = str(args.get("repo_path") or args.get("path") or "")
        depth = args.get("max_depth")
        if depth and depth != 3:  # 3 is default, only show if non-default
            return f"{path} · depth {depth}" if path else f"depth {depth}"
        return path

    # mcp.list_servers, task.list, skill.list, skill.run — no key args to show
    if name in ("mcp.list_servers", "task.list", "skill.list", "skill.run"):
        return ""

    # Generic fallback: show first 2 kv pairs
    parts = []
    for k, v in list(args.items())[:2]:
        parts.append(f"{k}={str(v)[:40]}")
    return ", ".join(parts)


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def _format_token_count(count: int) -> str:
    """Format token count as human-readable string."""
    if count < 1000:
        return str(count)
    return f"{count / 1000:.1f}k"


class StreamingDisplay:
    """Context manager for streaming agent output with tool progress.

    Shows a collapsible "Thinking" panel for transient progress text during
    streaming. Tool calls render as status lines. An animated spinner with
    dynamic verbs runs at the bottom. When streaming completes, the thinking
    panel collapses and only the final markdown answer remains.

    After streaming, the thinking text is preserved so the user can toggle
    it with Ctrl+T.

    Use ``StreamingDisplay._active_display`` to access the currently active
    instance for pause/resume from tool callbacks (e.g. agent.ask_user).
    """

    _active_display: "StreamingDisplay | None" = None

    def __init__(
        self,
        *,
        refresh_per_second: float = 10.0,
    ) -> None:
        self._live = Live(
            vertical_overflow="visible",
            refresh_per_second=refresh_per_second,
            console=get_console(),
        )
        self._text_parts: list[str] = []
        self._progress_parts: list[str] = []
        self._tools: list[dict] = []
        self._tool_count = 0
        self._finished = False
        self._thinking_collapsed = True  # Start collapsed — user toggles with Ctrl+T
        self._paused = False
        self._spinner_frame = 0
        self._spinner_verb = random.choice(SPINNER_VERBS)
        self._started_at = time.monotonic()
        self._token_count = 0

    def __enter__(self) -> "StreamingDisplay":
        StreamingDisplay._active_display = self
        self._live.start()
        return self

    def __exit__(self, *args: object) -> None:
        StreamingDisplay._active_display = None
        try:
            self._live.stop()
        except Exception:
            pass

    def pause(self) -> None:
        """Pause the live display. Safe to call when already paused."""
        if self._paused or self._finished:
            return
        try:
            self._live.stop()
        except Exception:
            pass
        self._paused = True
        # Print a newline to separate the prompt from the live display artifacts
        print()

    def resume(self) -> None:
        """Resume the live display after a pause. Safe to call when not paused."""
        if not self._paused or self._finished:
            return
        try:
            self._live.start()
            self._refresh()
        except Exception:
            pass
        self._paused = False

    def add_tokens(self, count: int) -> None:
        """Increment the output token counter."""
        self._token_count += count

    def add_text(self, text: str) -> None:
        """Append streaming text token to the answer area."""
        if self._finished:
            return
        self._text_parts.append(text)
        self._refresh()

    def add_progress(self, text: str) -> None:
        """Append transient progress text to the Thinking panel."""
        if self._finished:
            return
        self._progress_parts.append(text)
        self._refresh()

    @property
    def thinking_text(self) -> str:
        """Return collected thinking/reasoning text (available after streaming)."""
        return "".join(self._progress_parts).strip()

    @property
    def has_thinking(self) -> bool:
        return bool(self.thinking_text)

    def collapse_thinking(self) -> None:
        """Collapse the Thinking panel (called when final answer starts)."""
        self._thinking_collapsed = True
        self._refresh()

    def reset_progress(self) -> None:
        """Clear accumulated progress text — called at step boundaries to avoid duplicates."""
        self._progress_parts.clear()
        self._refresh()

    @property
    def tools_data(self) -> list[dict]:
        """Return tool call data for post-stream toggle display."""
        return list(self._tools)

    def start_tool(self, name: str, args: str = "") -> int:
        """Register a tool call starting — returns tool index."""
        if self._finished:
            return -1
        self._tool_count += 1
        formatted = _format_tool_args(name, args)
        self._tools.append({
            "name": name,
            "display": _TOOL_DISPLAY.get(name, name),
            "args": formatted,
            "status": "running",
        })
        self._refresh()
        return self._tool_count - 1

    def finish_tool(self, tool_index: int, *, ok: bool = True, result: str = "") -> None:
        """Mark a tool call as completed."""
        if tool_index < len(self._tools):
            self._tools[tool_index]["status"] = "ok" if ok else "error"
            self._tools[tool_index]["result"] = str(result)[:24000] if result else ""
        self._refresh()

    def finish(self, answer: str) -> None:
        """Collapse thinking panel, render final answer, stop live.

        Stop the live display FIRST to avoid line-count mismatch between
        the incremental plain-text render and the final markdown render.
        Then write the markdown answer directly to the console.
        """
        self._finished = True
        self._thinking_collapsed = True
        # Stop live before rendering final answer — avoids overlap artifacts
        # when the markdown render has fewer lines than the raw text render.
        try:
            self._live.stop()
        except Exception:
            pass

        body = answer.strip()
        if body:
            try:
                from .tui_utils import rich_to_ansi
                normalized = _normalize_markdown(body)
                md = Markdown(normalized, code_theme="material-darker")
                ansi = rich_to_ansi(md, width=100)
                if ansi:
                    import sys
                    sys.stdout.write(ansi)
                    sys.stdout.flush()
            except Exception:
                pass

    @staticmethod
    def render_thinking(
        thinking_text: str,
        *,
        expanded: bool = False,
    ) -> str:
        """Render thinking block for post-stream display.

        Returns a string suitable for printing with rich console markup.
        """
        if not thinking_text.strip():
            return ""

        if expanded:
            return (
                "\n[dim]────────── Thinking ──────────[/dim]\n"
                f"[dim]{thinking_text}[/dim]\n"
                "[dim]────────────────────────────────[/dim]"
            )
        else:
            line_count = thinking_text.count("\n") + 1
            return (
                f"\n[dim]┄ Thinking ({line_count} lines) — "
                "press [bold]Ctrl+T[/bold] to toggle ┄[/dim]"
            )

    @staticmethod
    def render_tools_summary(
        tools: list[dict],
        *,
        expanded: bool = False,
    ) -> str:
        """Render tool call summary for post-stream display.

        Returns a string suitable for printing with rich console markup.
        """
        if not tools:
            return ""

        if expanded:
            lines: list[str] = ["\n[dim]────────── Tools ──────────[/dim]"]
            for t in tools:
                icon = {"running": "●", "ok": "✓", "error": "✗"}.get(t.get("status", ""), "○")
                style = {"running": "yellow", "ok": "green", "error": "red"}.get(
                    t.get("status", ""), "dim"
                )
                display_name = t.get("display", t.get("name", "?"))
                args = t.get("args", "")
                line = f"[{style}]{icon} {display_name}[/{style}]"
                if args:
                    line += f"[dim]({args})[/dim]"
                result = t.get("result", "")
                if result:
                    line += f"[dim]  → {result[:300]}[/dim]"
                lines.append(line)
            lines.append("[dim]────────────────────────────────[/dim]")
            return "\n".join(lines)
        else:
            count = len(tools)
            return (
                f"\n[dim]┄ Tools ({count}) — "
                "press [bold]Ctrl+O[/bold] to toggle ┄[/dim]"
            )

    def _build_renderable(self):
        """Build the live renderable with Thinking panel + tool status + answer."""
        parts: list[RenderableType] = []

        # — Thinking panel: transient progress text (last N lines) —
        if self._progress_parts and not self._thinking_collapsed:
            progress_body = Text()
            # Show only the last 5 lines to keep the panel compact
            visible = self._progress_parts[-5:]
            progress_body.append(f"(showing last {len(visible)} of {len(self._progress_parts)} lines)\n", style="dim italic")
            for p in visible:
                progress_body.append(p.rstrip() + "\n", style="muted")
            progress_panel = RichPanel(
                progress_body,
                title="Thinking",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            )
            parts.append(progress_panel)

        # — Tool status lines —
        for t in self._tools:
            line = Text()
            icon = {"running": "●", "ok": "✓", "error": "✗"}.get(t["status"], "○")
            style = {"running": "tool", "ok": "success", "error": "error"}.get(t["status"], "muted")
            line.append(f"  {icon} ", style=style)
            line.append(t["display"], style="tool")
            if t["args"]:
                line.append(f"({t['args']})", style="muted")
            if t.get("result"):
                line.append(f"  → {t['result'][:200]}", style="muted")
            parts.append(line)

        # Answer text is NOT rendered here — it is shown once by finish()
        # after the live display stops. Rendering it here would duplicate it.

        # — Spinner status line —
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        frame = SPINNER_FRAMES[self._spinner_frame]
        elapsed = time.monotonic() - self._started_at
        # Rotate verb every ~8 seconds for variety
        verb_age = elapsed - getattr(self, '_last_verb_rotate', 0.0)
        if verb_age > 8.0:
            self._spinner_verb = random.choice(SPINNER_VERBS)
            self._last_verb_rotate = elapsed
        elapsed_str = _format_elapsed(elapsed)
        status = Text()
        status.append(f"  {frame} ", style="tool")
        status.append(f"{self._spinner_verb} ", style="muted")
        status.append(f"({elapsed_str}", style="dim")
        if self._token_count > 0:
            tk = _format_token_count(self._token_count)
            status.append(f" · ↓ {tk}", style="dim")
        status.append(")", style="dim")
        parts.append(status)

        return Group(*parts)

    def _build_renderable_ascii(self):
        """ASCII-safe fallback when _build_renderable triggers UnicodeEncodeError."""
        parts: list[RenderableType] = []

        if self._progress_parts and not self._thinking_collapsed:
            progress_body = Text()
            visible = self._progress_parts[-5:]
            for p in visible:
                safe = p.encode("ascii", errors="replace").decode("ascii")
                progress_body.append(safe.rstrip() + "\n", style="muted")
            progress_panel = RichPanel(
                progress_body,
                title="Thinking",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            )
            parts.append(progress_panel)

        for t in self._tools:
            line = Text()
            icon = {"running": ">", "ok": "+", "error": "!"}.get(t["status"], ".")
            style = {"running": "tool", "ok": "success", "error": "error"}.get(t["status"], "muted")
            line.append(f"  {icon} ", style=style)
            safe_display = t["display"].encode("ascii", errors="replace").decode("ascii")
            line.append(safe_display, style="tool")
            if t.get("result"):
                safe_result = t["result"][:200].encode("ascii", errors="replace").decode("ascii")
                line.append(f"  -> {safe_result}", style="muted")
            parts.append(line)

        # Answer text is NOT rendered here — shown once by finish()

        # Spinner status line (ASCII-safe)
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        elapsed = time.monotonic() - self._started_at
        verb_age = elapsed - getattr(self, '_last_verb_rotate', 0.0)
        if verb_age > 8.0:
            self._spinner_verb = random.choice(SPINNER_VERBS)
            self._last_verb_rotate = elapsed
        elapsed_str = _format_elapsed(elapsed)
        safe_verb = self._spinner_verb.encode("ascii", errors="replace").decode("ascii")
        parts.append(Text(f"  * {safe_verb} ({elapsed_str})", style="muted"))

        return Group(*parts)

    def _refresh(self) -> None:
        if self._finished or self._paused:
            return
        try:
            self._live.update(self._build_renderable())
        except UnicodeEncodeError:
            # Windows GBK console can't render certain Unicode chars;
            # fall back to ASCII-safe rendering
            try:
                self._live.update(self._build_renderable_ascii())
            except Exception:
                pass
        except Exception:
            pass
